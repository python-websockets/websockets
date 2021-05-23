// wait for "load" rather than "DOMContentLoaded"
// to ensure that the iframe has finished loading
window.addEventListener("load", () => {
    // create message channel to communicate
    // with the iframe
    const channel = new MessageChannel();
    const port1 = channel.port1;

    // receive WebSocket events from the iframe
    const expected = getExpectedEvents();
    var actual = [];
    port1.onmessage = ({ data }) => {
        // respond to messages
        if (data.type == "message") {
            port1.postMessage({
                type: "message",
                message: `Goodbye ${data.data.slice(6, -1)}.`,
            });
        }
        // run tests
        actual.push(data);
        testStep(expected, actual);
    };

    // send message channel to the iframe
    const iframe = document.querySelector("iframe");
    const origin = "http://localhost:8003";
    const ports = [channel.port2];
    iframe.contentWindow.postMessage("", origin, ports);

    // send token to the iframe
    port1.postMessage({
        type: "open",
        token: token,
    });
});
