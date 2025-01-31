import asyncio
import pathlib
import threading
import warnings


try:
    # Ignore deprecation warnings raised by mitmproxy dependencies at import time.
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="passlib")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="pyasn1")

    from mitmproxy.addons import core, next_layer, proxyauth, proxyserver, tlsconfig
    from mitmproxy.master import Master
    from mitmproxy.options import Options
except ImportError:
    pass


class RecordFlows:
    def __init__(self, on_running):
        self.running = on_running
        self.flows = []

    def websocket_start(self, flow):
        self.flows.append(flow)

    def get_flows(self):
        flows, self.flows[:] = self.flows[:], []
        return flows

    def reset_flows(self):
        self.flows = []


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

        cls.proxy_options = options = Options(mode=[cls.proxy_mode])
        cls.proxy_master = master = Master(options)
        master.addons.add(
            core.Core(),
            proxyauth.ProxyAuth(),
            proxyserver.Proxyserver(),
            next_layer.NextLayer(),
            tlsconfig.TlsConfig(),
            RecordFlows(on_running=cls.proxy_ready.set),
        )
        options.update(
            # Use test certificate for TLS between client and proxy.
            certs=[str(pathlib.Path(__file__).with_name("test_localhost.pem"))],
            # Disable TLS verification between proxy and upstream.
            ssl_insecure=True,
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

    def assertNumFlows(self, num_flows):
        record_flows = self.proxy_master.addons.get("recordflows")
        self.assertEqual(len(record_flows.get_flows()), num_flows)

    def tearDown(self):
        record_flows = self.proxy_master.addons.get("recordflows")
        record_flows.reset_flows()
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        cls.proxy_loop.call_soon_threadsafe(cls.proxy_stop.set_result, None)
        cls.proxy_thread.join()
        super().tearDownClass()
