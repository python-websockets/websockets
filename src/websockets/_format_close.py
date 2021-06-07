# See https://www.iana.org/assignments/websocket/websocket.xhtml
CLOSE_CODES = {
    1000: "OK",
    1001: "going away",
    1002: "protocol error",
    1003: "unsupported type",
    # 1004 is reserved
    1005: "no status code [internal]",
    1006: "connection closed abnormally [internal]",
    1007: "invalid data",
    1008: "policy violation",
    1009: "message too big",
    1010: "extension required",
    1011: "unexpected error",
    1012: "service restart",
    1013: "try again later",
    1014: "bad gateway",
    1015: "TLS failure [internal]",
}


def format_close(code: int, reason: str) -> str:
    """
    Display a human-readable version of the close code and reason.

    """
    if 3000 <= code < 4000:
        explanation = "registered"
    elif 4000 <= code < 5000:
        explanation = "private use"
    else:
        explanation = CLOSE_CODES.get(code, "unknown")
    result = f"code = {code} ({explanation}), "

    if reason:
        result += f"reason = {reason}"
    else:
        result += "no reason"

    return result
