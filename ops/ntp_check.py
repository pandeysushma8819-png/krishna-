from __future__ import annotations
import ntplib, time

def ntp_skew_seconds(server: str = "time.google.com", timeout: float = 3.0) -> tuple[str, float]:
    """
    Returns (server_used, skew_seconds = server_time - local_time).
    Positive skew => local clock is behind server.
    """
    client = ntplib.NTPClient()
    resp = client.request(server, version=3, timeout=timeout)
    server_time = resp.tx_time
    local_time = time.time()
    return server, float(server_time - local_time)
