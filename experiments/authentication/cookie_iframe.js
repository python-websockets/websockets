// receive message channel from the parent window
window.addEventListener("message", ({ ports }) => {
    const port2 = ports[0];
    var websocket;
    port2.onmessage = ({ data }) => {
        switch (data.type) {
            case "open":
                websocket = initWebSocket(data.token, port2);
                break;
            case "message":
                websocket.send(data.message);
                break;
            case "close":
                websocket.close(data.code, data.reason);
                break;
        }
    };
});

// open WebSocket connection and relay events to the parent window
function initWebSocket(token, port2) {
    document.cookie = `token=${token}; SameSite=Strict`;
    const websocket = new WebSocket("ws://localhost:8003/");

    websocket.addEventListener("open", ({ type }) => {
        port2.postMessage({ type });
    });
    websocket.addEventListener("message", ({ type, data }) => {
        port2.postMessage({ type, data });
    });
    websocket.addEventListener("close", ({ type, code, reason, wasClean }) => {
        port2.postMessage({ type, code, reason, wasClean });
    });

    return websocket;
}
