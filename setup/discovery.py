"""
WS-Discovery probe for ONVIF cameras on the local network.

Sends a multicast Probe to 239.255.255.250:3702 and collects
ProbeMatch responses. Returns a list of discovered devices with
their ONVIF service URLs.
"""
from __future__ import annotations

import logging
import socket
import struct
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MULTICAST_GRP = "239.255.255.250"
MULTICAST_PORT = 3702

_PROBE_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
    xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
    xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <s:Header>
    <a:MessageID>uuid:{msg_id}</a:MessageID>
    <a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>
    <a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>
  </s:Header>
  <s:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </s:Body>
</s:Envelope>"""


@dataclass
class DiscoveredCamera:
    host: str
    port: int
    xaddrs: str
    device_uuid: str | None = None
    model: str | None = None


def discover_onvif_cameras(timeout: float = 3.0) -> list[DiscoveredCamera]:
    """Send a WS-Discovery Probe and collect ONVIF camera responses."""
    msg_id = str(uuid.uuid4())
    probe = _PROBE_TEMPLATE.format(msg_id=msg_id).encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
    sock.settimeout(timeout)

    # Allow multicast loopback so we can discover emulators on localhost
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

    try:
        sock.sendto(probe, (MULTICAST_GRP, MULTICAST_PORT))
        logger.info("WS-Discovery probe sent to %s:%d", MULTICAST_GRP, MULTICAST_PORT)
    except Exception:
        logger.exception("Failed to send WS-Discovery probe")
        sock.close()
        return []

    seen: set[str] = set()
    cameras: list[DiscoveredCamera] = []

    while True:
        try:
            data, (src_ip, _) = sock.recvfrom(65536)
        except socket.timeout:
            break
        except Exception:
            logger.exception("WS-Discovery recv error")
            break

        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            continue

        action_el = root.find(
            ".//{http://schemas.xmlsoap.org/ws/2004/08/addressing}Action"
        )
        if action_el is None or "ProbeMatches" not in (action_el.text or ""):
            continue

        for match in root.findall(
            ".//{http://schemas.xmlsoap.org/ws/2005/04/discovery}ProbeMatch"
        ):
            xaddrs_el = match.find(
                "{http://schemas.xmlsoap.org/ws/2005/04/discovery}XAddrs"
            )
            if xaddrs_el is None or not xaddrs_el.text:
                continue

            xaddrs = xaddrs_el.text.strip().split()[0]

            addr_el = match.find(
                ".//{http://schemas.xmlsoap.org/ws/2004/08/addressing}Address"
            )
            device_uuid = addr_el.text.strip() if addr_el is not None and addr_el.text else None

            # Deduplicate by xaddrs
            if xaddrs in seen:
                continue
            seen.add(xaddrs)

            parsed = urlparse(xaddrs)
            host = parsed.hostname or src_ip
            port = parsed.port or 80

            cameras.append(DiscoveredCamera(
                host=host,
                port=port,
                xaddrs=xaddrs,
                device_uuid=device_uuid,
            ))
            logger.info("Discovered ONVIF camera at %s:%d", host, port)

    sock.close()
    logger.info("WS-Discovery complete: %d camera(s) found", len(cameras))
    return cameras
