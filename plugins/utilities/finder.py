# Copyright 2025 - Solely by BrotherBoard
# Intended for personal use only
# Bug? Feedback? Telegram >> @BroBordd

"""
Finder v4.1 - Find anyone

Refactored with proper packet structure and optimized for high-concurrency scanning.
Uses the same elegant enum system as Proto for maintainability and correctness.

Features:
- Proper packet structure using enums (readable and maintainable)
- Optimized lightweight join/roster/leave flow
- High-concurrency scanning via ThreadPoolExecutor
- Correct disconnect packets
- Sniffs out players without actually joining servers
"""

from json import dumps, loads
from concurrent.futures import ThreadPoolExecutor
from time import time, sleep
from enum import IntEnum
from random import randint, choice as CH, uniform as uf
from socket import socket, SOCK_DGRAM
from uuid import uuid4

from bascenev1 import connect_to_party as CON, protocol_version as PT
from bauiv1 import (
    get_ip_address_type as IPT, clipboard_set_text as COPY,
    get_special_widget as zw, containerwidget as ocw,
    screenmessage as push, buttonwidget as obw,
    scrollwidget as sw, imagewidget as iw,
    SpecialChar as sc, textwidget as tw,
    gettexture as gt, apptimer as teck,
    AppTimer as tuck, getsound as gs,
    getmesh as gm, charstr as cs,
    CallPartial
)
from babase import Plugin, app

plugman = dict(
    plugin_name="finder",
    description=(
        "Find anyone. Experimental. Useful if you are "
        "looking for someone, or just messing around. "
        "For full features, either check first lines "
        "of py file, or check source. Combine with "
        "Power plugin for better control."
    ),
    external_url="https://BroBordd.github.io/byBordd",
    authors=[
        {
            "name": "BrotherBoard",
            "email": "brobordd@gmail.com",
            "discord": "BrotherBoard"
        },
    ],
    version='4.1',
)

# ============================================================================
# PACKET ENUMS - Same elegant system as Proto
# ============================================================================


class PackEnum(IntEnum):
    """Base enum for all packet types"""
    @classmethod
    def get(cls):
        return [p for p in cls.__members__]

    def to_bytes(self):
        return bytes([self.value])


class Packet(PackEnum):
    """Main packet types"""
    P_SIMPLE_PING = 11
    P_SIMPLE_PONG = 12
    P_CLIENT_REQUEST = 24
    P_CLIENT_ACCEPT = 25
    P_CLIENT_DENY = 26
    P_CLIENT_DENY_VERSION_MISMATCH = 27
    P_CLIENT_DENY_ALREADY_IN_PARTY = 28
    P_CLIENT_DENY_PARTY_FULL = 29
    P_DISCONNECT_FROM_CLIENT_REQUEST = 32
    P_CLIENT_GAMEPACKET_COMPRESSED = 36
    P_HOST_GAMEPACKET_COMPRESSED = 37


class ScenePacket(PackEnum):
    """Scene packet types"""
    SP_HANDSHAKE_RESPONSE = 16
    SP_MESSAGE = 17
    SP_DISCONNECT = 19


class Message(PackEnum):
    """Message types"""
    M_NULL = 3
    M_PARTY_ROSTER = 9
    M_MULTIPART = 13
    M_MULTIPART_END = 14
    M_CLIENT_INFO = 18
    M_CLIENT_PLAYER_PROFILES_JSON = 21


class Extra(PackEnum):
    """Extra constants"""
    PROTOCOL_VERSION_LOW = 33
    PROTOCOL_VERSION_HIGH = 0
    ACK_EXTRA = 0
    DUMMY_MN_LOW = 240
    DUMMY_MN_HIGH = 255
    DUMMY_ACK_LOW = 240
    DUMMY_ACK_HIGH = 255

# ============================================================================
# OPTIMIZED PACKET BUILDER
# ============================================================================


class PacketBuilder:
    """Optimized packet construction for high-performance scanning"""

    def __init__(self):
        # Pre-build static data to avoid repeated encoding
        self._spec_data = self._build_spec()
        self._auth_data = self._build_auth()
        self._empty_profiles = self._build_empty_profiles()

    def _build_spec(self):
        """Build spec packet data once"""
        return dumps({
            's': dumps({
                'n': 'Finder',
                'a': '',
                'sn': ''
            }, separators=(',', ':')),
            'd': '69' * 20
        }, separators=(',', ':')).encode('utf-8')

    def _build_auth(self):
        """Build auth packet data once"""
        return dumps({
            'b': app.env.engine_build_number,
            'tk': '',
            'ph': ''
        }, separators=(',', ':')).encode('utf-8')

    def _build_empty_profiles(self):
        """Build empty profiles packet data once"""
        return dumps({}, separators=(',', ':')).encode('utf-8')

    def handshake_request(self, my_id: str) -> bytes:
        """Build client handshake request"""
        return (
            Packet.P_CLIENT_REQUEST.to_bytes() +
            Extra.PROTOCOL_VERSION_LOW.to_bytes() +
            Extra.PROTOCOL_VERSION_HIGH.to_bytes() +
            bytes.fromhex(my_id) +
            str(uuid4()).encode()
        )

    def handshake_response(self, server_id: str) -> bytes:
        """Build handshake response with spec"""
        return (
            Packet.P_CLIENT_GAMEPACKET_COMPRESSED.to_bytes() +
            bytes.fromhex(server_id) +
            ScenePacket.SP_HANDSHAKE_RESPONSE.to_bytes() +
            Extra.PROTOCOL_VERSION_LOW.to_bytes() +
            Extra.PROTOCOL_VERSION_HIGH.to_bytes() +
            self._spec_data
        )

    def auth_message(self, server_id: str) -> bytes:
        """Build auth message"""
        return (
            Packet.P_CLIENT_GAMEPACKET_COMPRESSED.to_bytes() +
            bytes.fromhex(server_id) +
            ScenePacket.SP_MESSAGE.to_bytes() +
            Extra.DUMMY_MN_LOW.to_bytes() +
            Extra.DUMMY_MN_HIGH.to_bytes() +
            Extra.DUMMY_ACK_LOW.to_bytes() +
            Extra.DUMMY_ACK_HIGH.to_bytes() +
            Extra.ACK_EXTRA.to_bytes() +
            Message.M_CLIENT_INFO.to_bytes() +
            self._auth_data
        )

    def profiles_message(self, server_id: str) -> bytes:
        """Build empty profiles message"""
        return (
            Packet.P_CLIENT_GAMEPACKET_COMPRESSED.to_bytes() +
            bytes.fromhex(server_id) +
            ScenePacket.SP_MESSAGE.to_bytes() +
            Extra.DUMMY_MN_LOW.to_bytes() +
            Extra.DUMMY_MN_HIGH.to_bytes() +
            Extra.DUMMY_ACK_LOW.to_bytes() +
            Extra.DUMMY_ACK_HIGH.to_bytes() +
            Extra.ACK_EXTRA.to_bytes() +
            Message.M_CLIENT_PLAYER_PROFILES_JSON.to_bytes() +
            self._empty_profiles
        )

    def null_message(self, server_id: str) -> bytes:
        """Build null message (final handshake)"""
        return (
            Packet.P_CLIENT_GAMEPACKET_COMPRESSED.to_bytes() +
            bytes.fromhex(server_id) +
            ScenePacket.SP_MESSAGE.to_bytes() +
            Extra.DUMMY_MN_LOW.to_bytes() +
            Extra.DUMMY_MN_HIGH.to_bytes() +
            Extra.DUMMY_ACK_LOW.to_bytes() +
            Extra.DUMMY_ACK_HIGH.to_bytes() +
            Extra.ACK_EXTRA.to_bytes() +
            Message.M_NULL.to_bytes()
        )

    def disconnect(self, server_id: str) -> bytes:
        """Build proper disconnect packet"""
        return (
            Packet.P_DISCONNECT_FROM_CLIENT_REQUEST.to_bytes() +
            bytes.fromhex(server_id)
        )

# ============================================================================
# OPTIMIZED SCANNER
# ============================================================================


def scan_server(address: str, port: int, packet_builder: PacketBuilder, index: int) -> tuple:
    """
    Lightweight scanner: ping -> handshake -> grab roster -> disconnect

    Optimized for scanning hundreds of servers in seconds:
    - Minimal socket operations
    - Pre-built packets
    - Fast timeout handling
    - Proper disconnect

    Returns: (index, ping_ms, roster_list)
    """
    ping_ms = 999
    roster = []
    sock = None

    try:
        # Create socket with tight timeout
        sock = socket(IPT(address), SOCK_DGRAM)
        sock.settimeout(2.5)

        addr_tuple = (address, port)

        # ---- PING ----
        ping_start = time()
        sock.sendto(Packet.P_SIMPLE_PING.to_bytes(), addr_tuple)

        data, recv_addr = sock.recvfrom(10)
        if data != Packet.P_SIMPLE_PONG.to_bytes() or recv_addr[0] != address:
            return (index, 999, [])

        ping_ms = (time() - ping_start) * 1000

        # ---- HANDSHAKE ----
        my_id = f'{(71 + randint(0, 150)):02x}'
        sock.sendto(packet_builder.handshake_request(my_id), addr_tuple)

        # Wait for accept
        shake = sock.recvfrom(1024)[0]
        if not shake.startswith(Packet.P_CLIENT_ACCEPT.to_bytes()):
            return (index, ping_ms, [])

        server_id = f'{shake[1]:02x}'

        # Flush host info
        sock.recvfrom(1024)

        # ---- MINIMAL JOIN SEQUENCE ----
        # Send only what's needed to get roster
        sock.sendto(packet_builder.handshake_response(server_id), addr_tuple)
        sock.sendto(packet_builder.auth_message(server_id), addr_tuple)
        sock.sendto(packet_builder.profiles_message(server_id), addr_tuple)
        sock.sendto(packet_builder.null_message(server_id), addr_tuple)

        # Flush acks
        sock.recvfrom(1024)
        sock.recvfrom(9)

        # ---- GRAB ROSTER ----
        roster_buffer = bytearray()
        collecting_multipart = False
        listen_start = time()

        while time() - listen_start < 1.5:  # Short timeout for roster
            try:
                packet = sock.recvfrom(2048)[0]

                if len(packet) < 9:
                    continue

                # Check for host game packet with message
                if (packet[0] == Packet.P_HOST_GAMEPACKET_COMPRESSED.value and
                        packet[2] == ScenePacket.SP_MESSAGE.value):

                    msg_type = packet[8]
                    msg_data = packet[9:]

                    # Direct roster message
                    if msg_type == Message.M_PARTY_ROSTER.value:
                        roster = loads(msg_data.rstrip(b'\x00').decode('utf-8'))
                        break

                    # Multipart roster start
                    elif msg_type == Message.M_MULTIPART.value:
                        if msg_data and msg_data[0] == Message.M_PARTY_ROSTER.value:
                            collecting_multipart = True
                            roster_buffer.clear()
                            roster_buffer.extend(msg_data[1:])
                        elif collecting_multipart:
                            roster_buffer.extend(msg_data)

                    # Multipart roster end
                    elif msg_type == Message.M_MULTIPART_END.value and collecting_multipart:
                        roster_buffer.extend(msg_data)
                        roster = loads(roster_buffer.rstrip(b'\x00').decode('utf-8'))
                        break

            except:
                break

        # ---- PROPER DISCONNECT ----
        sock.sendto(packet_builder.disconnect(server_id), addr_tuple)

    except:
        pass

    finally:
        if sock:
            sock.close()

    return (index, ping_ms, roster)

# ============================================================================
# FINDER UI
# ============================================================================


class Finder:
    VER = '4.0'
    COL1 = (0, 0.3, 0.3)
    COL2 = (0, 0.55, 0.55)
    COL3 = (0, 0.7, 0.7)
    COL4 = (0, 1, 1)
    COL5 = (1, 1, 0)

    # Class state
    PRO, MEM, ART, KIDS, IKIDS = [], [], [], [], []
    P2 = ARTT = SL = TIP = None
    BUSY = False
    FLT = ''

    def __init__(s, src):
        s.sust = None
        s.s1 = s.snd('powerup01')
        c = s.__class__
        z = (460, 400)

        c.P = cw(
            scale_origin_stack_offset=src.get_screen_space_center(),
            size=z,
            oac=s.bye
        )[0]

        sw(parent=c.P, size=z, border_opacity=0)

        tw(parent=c.P, text='Fetch all servers', color=s.COL4, position=(19, 359))

        bw(
            parent=c.P, position=(360, 343), size=(80, 39),
            label='Fetch', color=s.COL2, textcolor=s.COL4,
            oac=s.fresh
        )

        tw(
            parent=c.P, text='Sniff out players without joining',
            color=s.COL3, scale=0.8, position=(15, 330), maxwidth=320
        )

        iw(
            parent=c.P, size=(429, 1), position=(17, 330),
            texture=gt('white'), color=s.COL2
        )

        c.ARTT = tw(
            parent=c.P,
            text='' if c.ART else f'Finder v{c.VER}\n{CH(lmao())}',
            maxwidth=430, max_height=125,
            h_align='center', v_align='top',
            color=s.COL4, position=(205, 295)
        )

        iw(
            parent=c.P, size=(429, 1), position=(17, 200),
            texture=gt('white'), color=s.COL2
        )

        c.FT = tw(
            parent=c.P, position=(23, 150), size=(201, 35),
            text=c.FLT, editable=True, glow_type='uniform',
            allow_clear_button=False, v_align='center',
            color=s.COL4,
            description='Raw search - Matches wildcard to all strings'
        )

        s.ft2 = tw(parent=c.P, position=(26, 153), text='Search', color=s.COL3)

        p1 = sw(
            parent=c.P, position=(20, 18), size=(205, 122),
            border_opacity=0.4, color=s.COL4
        )

        c.P2 = ocw(parent=p1, size=(205, 1), background=False)

        s.pltip = tw(
            parent=c.P, position=(90, 100),
            text='Sniff some servers\nto collect players\nResults vary by\ntime and connection',
            color=s.COL4, maxwidth=175, h_align='center'
        )

        iw(
            parent=c.P, position=(235, 18), size=(205, 172),
            texture=gt('scrollWidget'),
            mesh_transparent=gm('softEdgeOutside'),
            opacity=0.4
        )

        s.tip = 'Select something to\nview server info'
        c.TIP = tw(
            parent=c.P, position=(310, 98),
            text=s.tip, color=s.COL4,
            maxwidth=170, h_align='center'
        )

        s.draw() if c.ART else 0
        s.up()
        c.SL and s.info(c.SL)
        c.FL = tuck(0.1, s.flup, repeat=True)

    def flup(s):
        c = s.__class__
        if not s.ft2.exists():
            c.FL = None
            return
        ct = tw(query=c.FT)
        tw(s.ft2, text=['Search', ''][bool(ct)])
        if ct != s.FLT:
            c.FLT = ct
            s.up()

    def hl(s, _, p):
        c = s.__class__
        c.SL = p
        for w in c.KIDS:
            tw(w, color=s.COL3)
        w = c.KIDS[_]
        tw(w, color=s.COL4)
        ocw(c.P2, visible_child=w)
        s.info(p)

    def info(s, p):
        c = s.__class__
        for _ in c.IKIDS:
            _.delete()
        c.IKIDS.clear()
        tw(c.TIP, text='')

        i = None
        for _ in c.MEM:
            for r in _.get('roster', []):
                try:
                    # Safely decode spec with error handling for control characters
                    spec_raw = r.get('spec', '')
                    if isinstance(spec_raw, bytes):
                        # Decode bytes, replacing invalid characters
                        spec_str = spec_raw.decode('utf-8', errors='replace')
                    else:
                        spec_str = str(spec_raw)

                    # Remove control characters before parsing
                    import re
                    # Remove all control characters except newline, carriage return, tab
                    spec_str = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', spec_str)

                    # Parse the cleaned JSON
                    spec = loads(spec_str)

                    if spec.get('n') == p:
                        i = _
                        pz = r['p']
                        break
                except (ValueError, KeyError, TypeError) as e:
                    # Skip malformed entries
                    continue

        if i is None:
            c.SL = None
            tw(c.TIP, text=s.tip)
            return

        for _ in range(3):
            t = str(i['nap'[_]])
            px = [250, 245, 375][_]
            py = [155, 115][bool(_)]
            sx = [175, 115, 55][_]
            c.IKIDS.append(tw(
                parent=c.P, position=(px, py),
                h_align='center', v_align='center',
                maxwidth=sx, text=t, color=s.COL4,
                size=(sx, 30), selectable=True,
                click_activate=True, glow_type='uniform',
                on_activate_call=CallPartial(s.copy, t)
            ))

        c.IKIDS.append(bw(
            parent=c.P, position=(253, 65), size=(166, 30),
            label=p, color=s.COL2, textcolor=s.COL4,
            oac=CallPartial(
                s.oke,
                '\n'.join([' | '.join([str(j) for j in _.values()]) for _ in pz]) or 'Nothing'
            )
        ))

        c.IKIDS.append(bw(
            parent=c.P, position=(253, 30), size=(166, 30),
            label='Connect', color=s.COL2, textcolor=s.COL4,
            oac=CallPartial(CON, i['a'], i['p'], False)
        ))

    def oke(s, t):
        TIP(t)
        s.ding(1, 1)

    def copy(s, t):
        s.ding(1, 1)
        TIP('Copied to clipboard!')
        COPY(t)

    def plys(s):
        z = []
        c = s.__class__
        for _ in c.MEM:
            a = _['a']
            if (r := _.get('roster', {})):
                for p in r:
                    try:
                        # Safely decode spec
                        spec_raw = p.get('spec', '')
                        if isinstance(spec_raw, bytes):
                            spec_str = spec_raw.decode('utf-8', errors='replace')
                        else:
                            spec_str = str(spec_raw)

                        # Remove control characters
                        import re
                        spec_str = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', spec_str)

                        ds = loads(spec_str)['n']
                    except (ValueError, KeyError, TypeError):
                        continue

                    0 if (ds == 'Finder' or (c.FLT and not s.chk(r))) else z.append((ds, a))
        return sorted(z, key=lambda _: _[0].startswith('Server'))

    def chk(s, r):
        t = s.__class__.FLT.lower()
        for _ in r:
            try:
                # Safely decode spec
                spec_raw = _.get('spec', '')
                if isinstance(spec_raw, bytes):
                    spec_str = spec_raw.decode('utf-8', errors='replace')
                else:
                    spec_str = str(spec_raw)

                # Remove control characters
                import re
                spec_str = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', spec_str)

                n = loads(spec_str)['n']
                if n != 'Finder' and t in n.lower():
                    return True
            except (ValueError, KeyError, TypeError):
                continue

            try:
                for p in _.get('p', []):
                    if t in p.get('nf', '').lower():
                        return True
            except (AttributeError, TypeError):
                continue
        return False

    def snd(s, t):
        l = gs(t)
        l.play()
        teck(uf(0.14, 0.18), l.stop)
        return l

    def bye(s):
        s.s1.stop()
        c = s.__class__
        ocw(c.P, transition='out_scale')
        l = s.snd('laser')
        def f(): return teck(0.01, f) if c.P else l.stop()
        f()

    def ding(s, *z):
        a = ['Small', '']
        for i, _ in enumerate(z):
            h = 'ding' + a[_]
            teck(i / 10, CallPartial(s.snd, h) if i < (len(z) - 1) else gs(h).play)

    def fresh(s):
        c = s.__class__
        if c.BUSY:
            TIP("Still busy!")
            s.ding(0, 0)
            return

        TIP('Scanning servers!\nThis should take a few seconds!\nYou can close this window.')
        c.ST = time()
        s.ding(1, 0)
        c.BUSY = True

        p = app.plus
        p.add_v1_account_transaction(
            {
                'type': 'PUBLIC_PARTY_QUERY',
                'proto': PT(),
                'lang': 'English'
            },
            callback=s.kang
        )
        p.run_v1_account_transactions()

    def kang(s, r):
        c = s.__class__
        c.MEM = r['l']
        c.ART = [cs(sc.OUYA_BUTTON_U)] * len(c.MEM)
        c.PRO.clear()

        # Create packet builder once for all scans
        packet_builder = PacketBuilder()

        # High concurrency for fast scanning
        executor = ThreadPoolExecutor(max_workers=256)

        c.THR = [
            executor.submit(
                scan_server,
                _['a'],
                _['p'],
                packet_builder,
                i
            ) for i, _ in enumerate(c.MEM)
        ]

        s.sus_starter()

    def sus_starter(s):
        if not s.sust:
            s.sust = tuck(0.01, s.sus, repeat=True)

    def sus(s):
        c = s.__class__

        # Process completed scans
        for future in c.THR[:]:
            if future.done():
                try:
                    index, ping, roster = future.result()
                    c.MEM[index]['ping'] = ping
                    c.MEM[index]['roster'] = roster

                    # Update art
                    c.ART[index] = (
                        cs(sc.OUYA_BUTTON_A) if ping == 999 else
                        cs(sc.OUYA_BUTTON_O) if ping < 100 else
                        cs(sc.OUYA_BUTTON_Y)
                    )

                    c.THR.remove(future)
                    s.draw() if c.ARTT.exists() else None
                except:
                    pass

        # Check if all done
        if not c.THR:
            s.sust = None
            s.done()

    def draw(s):
        c = s.__class__
        tw(c.ARTT, text=('\n'.join(''.join(c.ART[i:i + 40]) for i in range(0, len(s.ART), 40))))
        s.up()

    def up(s):
        c = s.__class__
        [_.delete() for _ in c.KIDS]
        c.KIDS.clear()
        pl = s.plys()
        s.pltip.delete() if pl else 0
        sy = max(len(pl) * 30, 90)
        ocw(c.P2, size=(205, sy))
        dun = 0
        for _, g in enumerate(pl):
            p, a = g
            tt = tw(
                parent=c.P2, size=(200, 30),
                selectable=True, click_activate=True,
                glow_type='uniform',
                color=[s.COL3, s.COL4][p == c.SL and not dun],
                text=p, position=(0, sy - 30 - 30 * _),
                maxwidth=175,
                on_activate_call=CallPartial(s.hl, _, p),
                v_align='center'
            )
            if not dun and p == c.SL:
                ocw(c.P2, visible_child=tt)
                dun = 1
            c.KIDS.append(tt)

    def done(s):
        c = s.__class__
        s.ding(0, 1)
        tt = time() - c.ST
        ln = len(s.MEM)
        ab = int(ln / tt)
        TIP(f'Finished!\nScanned {ln} servers in {round(tt, 2)} seconds!\nAbout {ab} server{"s" if ab != 1 else ""}/sec')
        s.__class__.BUSY = False

# ============================================================================
# UI HELPERS
# ============================================================================


bw = lambda *, oac=None, **k: obw(
    texture=gt('white'),
    on_activate_call=oac,
    enable_sound=False,
    **k
)

cw = lambda *, size=None, oac=None, **k: (p := ocw(
    parent=zw('overlay_stack'),
    background=False,
    transition='in_scale',
    size=size,
    on_outside_click_call=oac,
    **k
)) and (p, iw(
    parent=p,
    texture=gt('softRect'),
    size=(size[0] * 1.2, size[1] * 1.2),
    position=(-size[0] * 0.1, -size[1] * 0.1),
    opacity=0.55,
    color=(0, 0, 0)
), iw(
    parent=p,
    size=size,
    texture=gt('white'),
    color=Finder.COL1
))


def TIP(t): return push(t, Finder.COL3)


def lmao(): return [
    'Who are we looking for this time?',
    'Press on Fetch, and I\'ll do the rest.',
    'Let\'s legally stalk all servers!',
    'Let\'s list them all!',
    'Relax. We can find them.',
    'Lost your friend? Let\'s find them!',
    'Looking for players? I can help!',
    'Cool art appears here. Fetch already!',
    'Let\'s hear some "How did u find me!?"',
    'Ready as ever. Press on Fetch!',
    'Let\'s sniff out some packets!',
    'Who\'s there? I\'ll see myself!',
    'They can\'t hide!! Muahahaha-',
    'Why did I put a random tip here?',
    'We\'re having rosters for dinner!'
]

# ============================================================================
# PLUGIN EXPORT
# ============================================================================

# ba_meta require api 9
# ba_meta export babase.Plugin


class byBordd(Plugin):
    BTN = None
    def has_settings_ui(s): return True
    def show_settings_ui(s, w): return Finder(w)

    @classmethod
    def up(c):
        c.BTN.activate() if c.BTN.exists() else None

    def __init__(s):
        from bauiv1lib import party
        p = party.PartyWindow
        a = '__init__'
        o = getattr(p, a)
        setattr(p, a, lambda z, *a, **k: (o(z, *a, **k), s.make(z))[0])

    def make(s, z):
        sz = (80, 30)
        p = z._root_widget
        x, y = (-60, z._height - 45)
        iw(
            parent=p,
            size=(sz[0] * 1.34, sz[1] * 1.4),
            position=(x - sz[0] * 0.14, y - sz[1] * 0.20),
            texture=gt('softRect'),
            opacity=0.2,
            color=(0, 0, 0)
        )
        s.b = s.__class__.BTN = bw(
            parent=p,
            position=(x, y),
            label='Finder',
            color=Finder.COL1,
            textcolor=Finder.COL3,
            size=sz,
            oac=lambda: Finder(s.b)
        )
