"""Bounded discovery on directly connected private IPv4 networks; no login attempts."""
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor

import psutil

PORTS = (554, 8554, 37777, 34567)


def local_networks():
    stats = psutil.net_if_stats()
    result = []
    for interface, addresses in psutil.net_if_addrs().items():
        if interface not in stats or not stats[interface].isup:
            continue
        if any(word in interface.casefold() for word in ("vethernet", "loopback", "docker", "wsl", "vmware", "virtualbox")):
            continue
        for entry in addresses:
            if entry.family != socket.AF_INET or not entry.netmask:
                continue
            address = ipaddress.IPv4Address(entry.address)
            if not address.is_private or address.is_loopback or address.is_link_local:
                continue
            network = ipaddress.IPv4Network(f"{address}/{entry.netmask}", strict=False)
            limited = network.num_addresses > 256
            if limited:
                network = ipaddress.IPv4Network(f"{address}/24", strict=False)
            if network.prefixlen <= 30:
                result.append((str(network), str(address), limited))
    return list(dict.fromkeys(result))[:4]


def _probe(item):
    host, port = item
    try:
        with socket.create_connection((host, port), timeout=.35) as connection:
            if port in (554, 8554):
                connection.settimeout(.35)
                connection.sendall(f"OPTIONS rtsp://{host}:{port}/ RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
                try:
                    confirmed = connection.recv(1024).startswith(b"RTSP/")
                except OSError:
                    confirmed = False
                return host, port, confirmed
            return host, port, False
    except OSError:
        return None


def discover():
    networks = local_networks()
    if not networks:
        raise ValueError("Nenhuma rede IPv4 local ativa encontrada.")
    own = {address for _, address, _ in networks}
    targets = sorted({str(host) for network, _, _ in networks
                      for host in ipaddress.IPv4Network(network).hosts()} - own,
                     key=ipaddress.IPv4Address)
    devices = {}
    with ThreadPoolExecutor(max_workers=64, thread_name_prefix="camera-discovery") as pool:
        for found in pool.map(_probe, ((host, port) for host in targets for port in PORTS)):
            if found is None:
                continue
            host, port, confirmed = found
            device = devices.setdefault(host, {"ip": host, "ports": [], "rtsp_confirmed": False})
            device["ports"].append(port)
            device["rtsp_confirmed"] |= confirmed
    for device in devices.values():
        device["hint"] = ("Possível DVR Intelbras/Dahua" if 37777 in device["ports"] else
                          "Possível câmera iCSee/XM" if 34567 in device["ports"] else "Possível câmera/servidor RTSP")
        device["verified_video"] = False
    return {"networks": [network for network, _, _ in networks],
            "limited_to_24": any(limited for _, _, limited in networks),
            "devices": list(devices.values()),
            "note": "São candidatos por portas/RTSP, sem autenticação ou vídeo. Dispositivos desligados e de outras redes não aparecem; não há cadastro automático."}
