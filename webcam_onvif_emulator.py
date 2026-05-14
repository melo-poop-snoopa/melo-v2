#!/usr/bin/env python3
"""
Webcam ONVIF emulator — makes a local RTSP stream look like a security camera.

Simulates:
  1. WS-Discovery  — joins multicast 239.255.255.250:3702 and responds to Probe
                     messages with a ProbeMatch pointing at this HTTP server.
  2. ONVIF device service (/onvif/device_service) — responds to GetCapabilities
                     and GetServices with the media service URL.
  3. ONVIF media service (/onvif/media_service) — responds to GetProfiles (two
                     profiles, both pointing at the same RTSP stream) and
                     GetStreamUri.

Usage:
    python3 webcam_onvif_emulator.py --ip 192.168.1.42 --rtsp-url rtsp://127.0.0.1:8554/webcam

    --ip       Your machine's LAN IP (shown in discovery responses so the
               ONVIF client knows where to connect).  Use 127.0.0.1 only if
               your LMS also runs on the same machine AND your OS loops back
               multicast on loopback (not guaranteed on macOS).
    --port     HTTP port for the ONVIF service (default 8080).
    --rtsp-url RTSP URL that GetStreamUri will return (default rtsp://127.0.0.1:8554/webcam).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import socket
import struct
import threading
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Config ────────────────────────────────────────────────────────────────────

DEVICE_UUID    = str(uuid.uuid4())
MULTICAST_GRP  = "239.255.255.250"
MULTICAST_PORT = 3702

# ── WS-Discovery ──────────────────────────────────────────────────────────────

def _probe_match(relates_to: str, ip: str, port: int) -> bytes:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
    xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
    xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <s:Header>
    <a:MessageID>uuid:{uuid.uuid4()}</a:MessageID>
    <a:RelatesTo>{relates_to}</a:RelatesTo>
    <a:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:To>
    <a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</a:Action>
  </s:Header>
  <s:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <a:EndpointReference>
          <a:Address>urn:uuid:{DEVICE_UUID}</a:Address>
        </a:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>onvif://www.onvif.org/type/video_encoder</d:Scopes>
        <d:XAddrs>http://{ip}:{port}/onvif/device_service</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </s:Body>
</s:Envelope>""".encode()


def run_discovery(ip: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass  # not all platforms have SO_REUSEPORT

    sock.bind(("", MULTICAST_PORT))

    # Join multicast group on all interfaces
    mreq = struct.pack("4sL", socket.inet_aton(MULTICAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print(f"[WS-Discovery] Joined {MULTICAST_GRP}:{MULTICAST_PORT} — waiting for probes…")

    while True:
        try:
            data, (src_ip, src_port) = sock.recvfrom(65536)
        except Exception as exc:
            print(f"[WS-Discovery] recvfrom error: {exc}")
            continue

        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            continue

        action_el = root.find(
            ".//{http://schemas.xmlsoap.org/ws/2004/08/addressing}Action"
        )
        if action_el is None or "Probe" not in (action_el.text or ""):
            continue

        msg_id_el = root.find(
            ".//{http://schemas.xmlsoap.org/ws/2004/08/addressing}MessageID"
        )
        relates_to = (msg_id_el.text or f"uuid:{uuid.uuid4()}").strip() if msg_id_el is not None else f"uuid:{uuid.uuid4()}"

        print(f"[WS-Discovery] Probe from {src_ip}:{src_port} — sending ProbeMatch")
        try:
            sock.sendto(_probe_match(relates_to, ip, port), (src_ip, src_port))
        except Exception as exc:
            print(f"[WS-Discovery] send error: {exc}")


# ── ONVIF SOAP responses ───────────────────────────────────────────────────────

def _get_capabilities(ip: str, port: int) -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
    xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tds:GetCapabilitiesResponse>
      <tds:Capabilities>
        <tt:Media>
          <tt:XAddr>http://{ip}:{port}/onvif/media_service</tt:XAddr>
          <tt:StreamingCapabilities>
            <tt:RTPMulticast>false</tt:RTPMulticast>
            <tt:RTP_TCP>true</tt:RTP_TCP>
            <tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP>
          </tt:StreamingCapabilities>
        </tt:Media>
      </tds:Capabilities>
    </tds:GetCapabilitiesResponse>
  </s:Body>
</s:Envelope>"""


def _get_services(ip: str, port: int) -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
    xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tds:GetServicesResponse>
      <tds:Service>
        <tds:Namespace>http://www.onvif.org/ver10/media/wsdl</tds:Namespace>
        <tds:XAddr>http://{ip}:{port}/onvif/media_service</tds:XAddr>
        <tds:Version>
          <tt:Major>2</tt:Major>
          <tt:Minor>6</tt:Minor>
        </tds:Version>
      </tds:Service>
    </tds:GetServicesResponse>
  </s:Body>
</s:Envelope>"""


# Two profiles: profile[0] = main stream, profile[1] = sub-stream (both point
# at the same webcam RTSP URL since there is only one physical source).
# Your LMS uses motion_monitor_profile=1 (sub-stream) for motion and
# profile[0] for recording — both will get the same feed, which is fine for testing.
_GET_PROFILES = """\
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
    xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetProfilesResponse>
      <trt:Profiles token="Profile_1" fixed="true">
        <tt:Name>MainStream</tt:Name>
        <tt:VideoSourceConfiguration token="VSC_1">
          <tt:Name>VideoSource_Main</tt:Name>
          <tt:UseCount>1</tt:UseCount>
          <tt:SourceToken>VideoSource_1</tt:SourceToken>
          <tt:Bounds x="0" y="0" width="1280" height="720"/>
        </tt:VideoSourceConfiguration>
        <tt:VideoEncoderConfiguration token="VEC_1">
          <tt:Name>Encoder_Main</tt:Name>
          <tt:UseCount>1</tt:UseCount>
          <tt:Encoding>H264</tt:Encoding>
          <tt:Resolution>
            <tt:Width>1280</tt:Width>
            <tt:Height>720</tt:Height>
          </tt:Resolution>
          <tt:Quality>5</tt:Quality>
          <tt:RateControl>
            <tt:FrameRateLimit>30</tt:FrameRateLimit>
            <tt:EncodingInterval>1</tt:EncodingInterval>
            <tt:BitrateLimit>4096</tt:BitrateLimit>
          </tt:RateControl>
        </tt:VideoEncoderConfiguration>
      </trt:Profiles>
      <trt:Profiles token="Profile_2" fixed="true">
        <tt:Name>SubStream</tt:Name>
        <tt:VideoSourceConfiguration token="VSC_1">
          <tt:Name>VideoSource_Sub</tt:Name>
          <tt:UseCount>1</tt:UseCount>
          <tt:SourceToken>VideoSource_1</tt:SourceToken>
          <tt:Bounds x="0" y="0" width="640" height="480"/>
        </tt:VideoSourceConfiguration>
        <tt:VideoEncoderConfiguration token="VEC_2">
          <tt:Name>Encoder_Sub</tt:Name>
          <tt:UseCount>1</tt:UseCount>
          <tt:Encoding>H264</tt:Encoding>
          <tt:Resolution>
            <tt:Width>640</tt:Width>
            <tt:Height>480</tt:Height>
          </tt:Resolution>
          <tt:Quality>3</tt:Quality>
          <tt:RateControl>
            <tt:FrameRateLimit>15</tt:FrameRateLimit>
            <tt:EncodingInterval>1</tt:EncodingInterval>
            <tt:BitrateLimit>1024</tt:BitrateLimit>
          </tt:RateControl>
        </tt:VideoEncoderConfiguration>
      </trt:Profiles>
    </trt:GetProfilesResponse>
  </s:Body>
</s:Envelope>"""


def _get_stream_uri(rtsp_url: str, rtsp_user: str = "", rtsp_pass: str = "") -> str:
    if rtsp_user:
        parsed = urllib.parse.urlparse(rtsp_url)
        netloc = f"{urllib.parse.quote(rtsp_user, safe='')}:{urllib.parse.quote(rtsp_pass, safe='')}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        rtsp_url = parsed._replace(netloc=netloc).geturl()
    return _get_stream_uri_xml(rtsp_url)


def _get_stream_uri_xml(rtsp_url: str) -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
    xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetStreamUriResponse>
      <trt:MediaUri>
        <tt:Uri>{rtsp_url}</tt:Uri>
        <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
        <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
        <tt:Timeout>PT0S</tt:Timeout>
      </trt:MediaUri>
    </trt:GetStreamUriResponse>
  </s:Body>
</s:Envelope>"""


# ── Auth helpers ──────────────────────────────────────────────────────────────

_WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
_WSU_NS  = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"

_SOAP_FAULT_UNAUTHORIZED = """\
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    <s:Fault>
      <s:Code><s:Value>s:Sender</s:Value></s:Code>
      <s:Reason><s:Text xml:lang="en">NotAuthorized</s:Text></s:Reason>
    </s:Fault>
  </s:Body>
</s:Envelope>""".encode()


def _check_wsse_auth(body: str, expected_user: str, expected_pass: str) -> bool:
    """
    Validate WS-Security UsernameToken.  Supports both PasswordDigest and
    PasswordText so the emulator works regardless of client auth mode.

    PasswordDigest formula (ONVIF / WS-UsernameToken spec):
        digest = Base64( SHA-1( nonce_bytes + created_utf8 + password_utf8 ) )
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return False

    username_el = root.find(f".//{{{_WSSE_NS}}}Username")
    password_el = root.find(f".//{{{_WSSE_NS}}}Password")
    nonce_el    = root.find(f".//{{{_WSSE_NS}}}Nonce")
    created_el  = root.find(f".//{{{_WSU_NS}}}Created")

    if username_el is None or password_el is None:
        return False

    username = (username_el.text or "").strip()
    if username != expected_user:
        return False

    password_text = (password_el.text or "").strip()
    password_type = password_el.get("Type", "")

    # PasswordText — plain comparison
    if "PasswordText" in password_type or (not password_type and nonce_el is None):
        return password_text == expected_pass

    # PasswordDigest — recompute and compare
    if nonce_el is None or created_el is None:
        return False
    try:
        nonce_bytes   = base64.b64decode(nonce_el.text or "")
        created_bytes = (created_el.text or "").encode("utf-8")
        pass_bytes    = expected_pass.encode("utf-8")
        digest        = base64.b64encode(
            hashlib.sha1(nonce_bytes + created_bytes + pass_bytes).digest()
        ).decode()
        return digest == password_text
    except Exception:
        return False


# ── HTTP handler ──────────────────────────────────────────────────────────────

class ONVIFHandler(BaseHTTPRequestHandler):
    """Minimal ONVIF SOAP handler.  WS-Security UsernameToken credentials are
    validated when --username/--password are supplied; otherwise open access."""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode(errors="replace")

        ip        = self.server.emulator_ip       # type: ignore[attr-defined]
        port      = self.server.emulator_port     # type: ignore[attr-defined]
        rtsp_url  = self.server.rtsp_url          # type: ignore[attr-defined]
        req_user  = self.server.onvif_username    # type: ignore[attr-defined]
        req_pass  = self.server.onvif_password    # type: ignore[attr-defined]
        rtsp_user = self.server.rtsp_user         # type: ignore[attr-defined]
        rtsp_pass = self.server.rtsp_pass         # type: ignore[attr-defined]

        # Enforce WS-Security when credentials are configured
        if req_user:
            if not _check_wsse_auth(body, req_user, req_pass):
                print(f"[ONVIF HTTP] Unauthorized request from {self.client_address[0]}")
                self.send_response(401)
                self.send_header("Content-Type", "application/soap+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(_SOAP_FAULT_UNAUTHORIZED)))
                self.end_headers()
                self.wfile.write(_SOAP_FAULT_UNAUTHORIZED)
                return

        if "GetCapabilities" in body:
            xml = _get_capabilities(ip, port)
            action = "GetCapabilities"
        elif "GetServices" in body:
            xml = _get_services(ip, port)
            action = "GetServices"
        elif "GetProfiles" in body:
            xml = _GET_PROFILES
            action = "GetProfiles"
        elif "GetStreamUri" in body:
            xml = _get_stream_uri(rtsp_url, rtsp_user, rtsp_pass)
            action = "GetStreamUri"
        else:
            # Unknown action — return an empty 200 so the client doesn't hang
            self.send_response(200)
            self.send_header("Content-Type", "application/soap+xml; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            print(f"[ONVIF HTTP] Unknown SOAP body from {self.client_address[0]}")
            return

        print(f"[ONVIF HTTP] {self.client_address[0]} → {action}")
        encoded = xml.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/soap+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args: object) -> None:
        pass  # silence default Apache-style access log


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Webcam ONVIF emulator")
    parser.add_argument(
        "--ip",
        default="127.0.0.1",
        help="LAN IP to advertise in discovery responses (use your machine's real IP, e.g. 192.168.1.42)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="HTTP port for the ONVIF service (default: 8080)",
    )
    parser.add_argument(
        "--rtsp-url",
        default="rtsp://127.0.0.1:8554/webcam",
        help="RTSP URL returned by GetStreamUri (default: rtsp://127.0.0.1:8554/webcam)",
    )
    parser.add_argument(
        "--username",
        default="",
        help="ONVIF username to require in WS-Security headers (default: none → no auth)",
    )
    parser.add_argument(
        "--password",
        default="",
        help="ONVIF password to require in WS-Security headers (default: none → no auth)",
    )
    parser.add_argument(
        "--rtsp-user",
        default="",
        help="Username to embed in the RTSP URL returned by GetStreamUri (default: none)",
    )
    parser.add_argument(
        "--rtsp-pass",
        default="",
        help="Password to embed in the RTSP URL returned by GetStreamUri (default: none)",
    )
    args = parser.parse_args()

    onvif_auth_status = f"{args.username} / *** (enforced)" if args.username else "disabled (no auth)"
    rtsp_auth_status  = f"embedded in URL ({args.rtsp_user}:***)" if args.rtsp_user else "none embedded"

    print("=" * 60)
    print("Webcam ONVIF Emulator")
    print(f"  Device UUID  : {DEVICE_UUID}")
    print(f"  Advertised IP: {args.ip}")
    print(f"  ONVIF HTTP   : http://{args.ip}:{args.port}/onvif/device_service")
    print(f"  RTSP URL     : {args.rtsp_url}")
    print(f"  ONVIF Auth   : {onvif_auth_status}")
    print(f"  RTSP Auth    : {rtsp_auth_status}")
    if args.rtsp_user:
        print("  NOTE: Configure your RTSP server (MediaMTX/ffmpeg) with the")
        print(f"        same credentials ({args.rtsp_user}:***) to protect the stream itself.")
    print("=" * 60)
    print()

    # WS-Discovery runs in a background daemon thread
    disc_thread = threading.Thread(
        target=run_discovery,
        args=(args.ip, args.port),
        daemon=True,
        name="ws-discovery",
    )
    disc_thread.start()

    # ONVIF HTTP server runs in the main thread
    server = HTTPServer(("0.0.0.0", args.port), ONVIFHandler)
    server.emulator_ip      = args.ip          # type: ignore[attr-defined]
    server.emulator_port    = args.port        # type: ignore[attr-defined]
    server.rtsp_url         = args.rtsp_url    # type: ignore[attr-defined]
    server.onvif_username   = args.username    # type: ignore[attr-defined]
    server.onvif_password   = args.password    # type: ignore[attr-defined]
    server.rtsp_user        = args.rtsp_user   # type: ignore[attr-defined]
    server.rtsp_pass        = args.rtsp_pass   # type: ignore[attr-defined]

    print(f"[ONVIF HTTP] Listening on 0.0.0.0:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
