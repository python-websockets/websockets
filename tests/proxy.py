import asyncio
import pathlib
import ssl
import threading
import warnings


try:
    # Ignore deprecation warnings raised by mitmproxy dependencies at import time.
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="passlib")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="pyasn1")

    from mitmproxy import ctx
    from mitmproxy.addons import core, next_layer, proxyauth, proxyserver, tlsconfig
    from mitmproxy.http import Response
    from mitmproxy.master import Master
    from mitmproxy.options import CONF_BASENAME, CONF_DIR, Options
except ImportError:
    pass


class RecordFlows:
    def __init__(self, on_running):
        self.running = on_running
        self.http_connects = []
        self.tcp_flows = []

    def http_connect(self, flow):
        self.http_connects.append(flow)

    def tcp_start(self, flow):
        self.tcp_flows.append(flow)

    def get_http_connects(self):
        http_connects, self.http_connects[:] = self.http_connects[:], []
        return http_connects

    def get_tcp_flows(self):
        tcp_flows, self.tcp_flows[:] = self.tcp_flows[:], []
        return tcp_flows

    def reset(self):
        self.http_connects = []
        self.tcp_flows = []


class AlterRequest:
    def load(self, loader):
        loader.add_option(
            name="break_http_connect",
            typespec=bool,
            default=False,
            help="Respond to HTTP CONNECT requests with a 999 status code.",
        )
        loader.add_option(
            name="close_http_connect",
            typespec=bool,
            default=False,
            help="Do not respond to HTTP CONNECT requests.",
        )

    def http_connect(self, flow):
        if ctx.options.break_http_connect:
            # mitmproxy can send a response with a status code not between 100
            # and 599, while websockets treats it as a protocol error.
            # This is used for testing HTTP parsing errors.
            flow.response = Response.make(999, "not a valid HTTP response")
        if ctx.options.close_http_connect:
            flow.kill()


class ProxyMixin:
    """
    Run mitmproxy in a background thread.

    While it's uncommon to run two event loops in two threads, tests for the
    asyncio implementation rely on this class too because it starts an event
    loop for mitm proxy once, then a new event loop for each test.
    """

    proxy_mode = None

    @classmethod
    async def run_proxy(cls):
        cls.proxy_loop = loop = asyncio.get_event_loop()
        cls.proxy_stop = stop = loop.create_future()

        cls.proxy_options = options = Options(
            mode=[cls.proxy_mode],
            # Don't intercept connections, but record them.
            ignore_hosts=["^localhost:", "^127.0.0.1:", "^::1:"],
            # This option requires mitmproxy 11.0.0, which requires Python 3.11.
            show_ignored_hosts=True,
        )
        cls.proxy_master = master = Master(options)
        master.addons.add(
            core.Core(),
            proxyauth.ProxyAuth(),
            proxyserver.Proxyserver(),
            next_layer.NextLayer(),
            tlsconfig.TlsConfig(),
            RecordFlows(on_running=cls.proxy_ready.set),
            AlterRequest(),
        )

        task = loop.create_task(cls.proxy_master.run())
        await stop

        for server in master.addons.get("proxyserver").servers:
            await server.stop()
        master.shutdown()
        await task

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Ignore deprecation warnings raised by mitmproxy at run time.
        warnings.filterwarnings(
            "ignore", category=DeprecationWarning, module="mitmproxy"
        )

        cls.proxy_ready = threading.Event()
        cls.proxy_thread = threading.Thread(target=asyncio.run, args=(cls.run_proxy(),))
        cls.proxy_thread.start()
        cls.proxy_ready.wait()

        certificate = pathlib.Path(CONF_DIR) / f"{CONF_BASENAME}-ca-cert.pem"
        certificate = certificate.expanduser()
        cls.proxy_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cls.proxy_context.load_verify_locations(bytes(certificate))

    def get_http_connects(self):
        return self.proxy_master.addons.get("recordflows").get_http_connects()

    def get_tcp_flows(self):
        return self.proxy_master.addons.get("recordflows").get_tcp_flows()

    def assertNumFlows(self, num_tcp_flows):
        self.assertEqual(len(self.get_tcp_flows()), num_tcp_flows)

    def tearDown(self):
        record_tcp_flows = self.proxy_master.addons.get("recordflows")
        record_tcp_flows.reset()
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        cls.proxy_loop.call_soon_threadsafe(cls.proxy_stop.set_result, None)
        cls.proxy_thread.join()
        super().tearDownClass()
