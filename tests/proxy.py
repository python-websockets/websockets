import asyncio
import contextlib
import pathlib
import threading
import warnings


warnings.filterwarnings("ignore", category=DeprecationWarning, module="mitmproxy")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="passlib")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pyasn1")

try:
    from mitmproxy.addons import core, next_layer, proxyauth, proxyserver, tlsconfig
    from mitmproxy.master import Master
    from mitmproxy.options import Options
except ImportError:
    pass


class RecordFlows:
    def __init__(self):
        self.ready = asyncio.get_running_loop().create_future()
        self.flows = []

    def running(self):
        self.ready.set_result(None)

    def websocket_start(self, flow):
        self.flows.append(flow)

    def get_flows(self):
        flows, self.flows[:] = self.flows[:], []
        return flows


@contextlib.asynccontextmanager
async def async_proxy(mode, **config):
    options = Options(mode=mode)
    master = Master(options)
    record_flows = RecordFlows()
    master.addons.add(
        core.Core(),
        proxyauth.ProxyAuth(),
        proxyserver.Proxyserver(),
        next_layer.NextLayer(),
        tlsconfig.TlsConfig(),
        record_flows,
    )
    config.update(
        # Use our test certificate for TLS between client and proxy
        # and disable TLS verification between proxy and upstream.
        certs=[str(pathlib.Path(__file__).with_name("test_localhost.pem"))],
        ssl_insecure=True,
    )
    options.update(**config)

    asyncio.create_task(master.run())
    try:
        await record_flows.ready
        yield record_flows
    finally:
        for server in master.addons.get("proxyserver").servers:
            await server.stop()
        master.shutdown()


@contextlib.contextmanager
def sync_proxy(mode, **config):
    loop = None
    test_done = None
    proxy_ready = threading.Event()
    record_flows = None

    async def proxy_coroutine():
        nonlocal loop, test_done, proxy_ready, record_flows
        loop = asyncio.get_running_loop()
        test_done = loop.create_future()
        async with async_proxy(mode, **config) as record_flows:
            proxy_ready.set()
            await test_done

    proxy_thread = threading.Thread(target=asyncio.run, args=(proxy_coroutine(),))
    proxy_thread.start()
    try:
        proxy_ready.wait()
        yield record_flows
    finally:
        loop.call_soon_threadsafe(test_done.set_result, None)
        proxy_thread.join()
