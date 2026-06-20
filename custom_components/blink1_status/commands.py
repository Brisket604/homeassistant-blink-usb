"""Builders et parsers pour le protocole HID blink(1).

Module pur (sans I/O) contenant toute la logique de construction et de
parsing des feature reports HID blink(1).
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constantes du protocole
# ---------------------------------------------------------------------------

REPORT_ID = 0x01

CMD_SET_RGB_NOW = 0x6E        # 'n'
CMD_FADE_TO_RGB = 0x63        # 'c'
CMD_READ_COLOR = 0x72         # 'r'
CMD_GET_VERSION = 0x76        # 'v'
CMD_SET_PATTERN_LINE = 0x50   # 'P'
CMD_READ_PATTERN_LINE = 0x52  # 'R'
CMD_SAVE_PATTERNS = 0x57      # 'W'
CMD_PLAY_LOOP = 0x70          # 'p'
CMD_PLAY_STATE = 0x53         # 'S'
CMD_SERVER_TICKLE = 0x44      # 'D'

MAX_PATTERN_POS = 31
MAX_LED_INDEX = 2
MAX_FADE_MS = 655350
MAX_RGB = 255

# ---------------------------------------------------------------------------
# Dataclasses de résultat
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RGBColor:
    """Couleur RGB lue depuis le dispositif."""

    r: int  # 0-255
    g: int  # 0-255
    b: int  # 0-255


@dataclass(frozen=True, slots=True)
class PatternLine:
    """Une ligne de pattern lue depuis le dispositif."""

    r: int        # 0-255
    g: int        # 0-255
    b: int        # 0-255
    fade_ms: int  # 0-655350, multiple de 10


@dataclass(frozen=True, slots=True)
class PlayState:
    """État de lecture des patterns."""

    playing: bool
    play_start: int   # 0-31
    play_end: int     # 0-31
    play_count: int   # 0-255
    play_pos: int     # 0-31


# ---------------------------------------------------------------------------
# Fonctions de validation
# ---------------------------------------------------------------------------


def validate_rgb(r: int, g: int, b: int) -> None:
    """Valide que les composantes RGB sont dans l'intervalle 0-255.

    Raises:
        ValueError: Si une ou plusieurs valeurs sont hors de l'intervalle.
    """
    out_of_range: list[str] = []
    if not (0 <= r <= MAX_RGB):
        out_of_range.append(f"r={r}")
    if not (0 <= g <= MAX_RGB):
        out_of_range.append(f"g={g}")
    if not (0 <= b <= MAX_RGB):
        out_of_range.append(f"b={b}")
    if out_of_range:
        raise ValueError(
            f"RGB values must be in 0-{MAX_RGB}, got invalid: "
            + ", ".join(out_of_range)
        )


def validate_led_index(led_n: int) -> None:
    """Valide que le LED_Index est dans l'intervalle 0-2.

    Args:
        led_n: Index de la LED (0=toutes, 1=supérieure, 2=inférieure).

    Raises:
        ValueError: Si la valeur est hors de l'intervalle 0-2.
    """
    if not (0 <= led_n <= MAX_LED_INDEX):
        raise ValueError(
            f"LED index must be in 0-{MAX_LED_INDEX}, got {led_n}"
        )


def validate_position(pos: int) -> None:
    """Valide que la position de pattern est dans l'intervalle 0-31.

    Args:
        pos: Position du pattern (0-31).

    Raises:
        ValueError: Si la valeur est hors de l'intervalle 0-31.
    """
    if not (0 <= pos <= MAX_PATTERN_POS):
        raise ValueError(
            f"Pattern position must be in 0-{MAX_PATTERN_POS}, got {pos}"
        )


def validate_fade_ms(fade_ms: int) -> None:
    """Valide que le fade time est dans l'intervalle 0-655350ms.

    Args:
        fade_ms: Durée du fondu en millisecondes.

    Raises:
        ValueError: Si la valeur est négative ou supérieure à 655350.
    """
    if not (0 <= fade_ms <= MAX_FADE_MS):
        raise ValueError(
            f"Fade time must be in 0-{MAX_FADE_MS}ms, got {fade_ms}"
        )


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _encode_time(ms: int) -> tuple[int, int]:
    """Encode un temps en millisecondes vers (th, tl) big-endian.

    Le temps est divisé par 10 pour obtenir les unités du protocole blink(1),
    puis encodé sur 2 octets big-endian.

    Args:
        ms: Temps en millisecondes (doit être préalablement validé).

    Returns:
        Tuple (th, tl) avec th = octet haut, tl = octet bas.
    """
    fade_units = ms // 10
    th = (fade_units >> 8) & 0xFF
    tl = fade_units & 0xFF
    return th, tl


# ---------------------------------------------------------------------------
# Builders de commandes (écriture)
# ---------------------------------------------------------------------------


def build_set_rgb_now(r: int, g: int, b: int, led_n: int = 0) -> bytes:
    """Construit le Feature_Report pour définir une couleur RGB instantanément.

    Args:
        r: Composante rouge (0-255).
        g: Composante verte (0-255).
        b: Composante bleue (0-255).
        led_n: Index de la LED cible (0=toutes, 1=supérieure, 2=inférieure).

    Returns:
        bytes: Feature_Report de 9 octets.

    Raises:
        ValueError: Si les paramètres sont hors de leurs bornes valides.
    """
    validate_rgb(r, g, b)
    validate_led_index(led_n)
    return bytes([REPORT_ID, CMD_SET_RGB_NOW, r, g, b, 0x00, 0x00, led_n, 0x00])


def build_fade_to_rgb(
    r: int, g: int, b: int, fade_ms: int = 100, led_n: int = 0
) -> bytes:
    """Construit le Feature_Report pour un fondu vers une couleur RGB.

    Args:
        r: Composante rouge (0-255).
        g: Composante verte (0-255).
        b: Composante bleue (0-255).
        fade_ms: Durée du fondu en millisecondes (0-655350).
        led_n: Index de la LED cible (0=toutes, 1=supérieure, 2=inférieure).

    Returns:
        bytes: Feature_Report de 9 octets.

    Raises:
        ValueError: Si les paramètres sont hors de leurs bornes valides.
    """
    validate_rgb(r, g, b)
    validate_fade_ms(fade_ms)
    validate_led_index(led_n)
    th, tl = _encode_time(fade_ms)
    return bytes([REPORT_ID, CMD_FADE_TO_RGB, r, g, b, th, tl, led_n, 0x00])


def build_set_pattern_line(
    r: int, g: int, b: int, fade_ms: int, pos: int
) -> bytes:
    """Construit le Feature_Report pour écrire une ligne de pattern.

    Args:
        r: Composante rouge (0-255).
        g: Composante verte (0-255).
        b: Composante bleue (0-255).
        fade_ms: Durée du fondu en millisecondes (0-655350).
        pos: Position du pattern en mémoire (0-31).

    Returns:
        bytes: Feature_Report de 9 octets.

    Raises:
        ValueError: Si les paramètres sont hors de leurs bornes valides.
    """
    validate_rgb(r, g, b)
    validate_fade_ms(fade_ms)
    validate_position(pos)
    th, tl = _encode_time(fade_ms)
    return bytes([REPORT_ID, CMD_SET_PATTERN_LINE, r, g, b, th, tl, pos, 0x00])


def build_save_patterns() -> bytes:
    """Construit le Feature_Report pour sauvegarder les patterns en flash.

    Returns:
        bytes: Feature_Report de 9 octets.
    """
    return bytes(
        [REPORT_ID, CMD_SAVE_PATTERNS, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    )


def build_play_loop(start: int, end: int, count: int = 0) -> bytes:
    """Construit le Feature_Report pour démarrer la lecture en boucle.

    Args:
        start: Position de début du pattern (0-31, doit être < end).
        end: Position de fin du pattern (0-31, doit être > start).
        count: Nombre de répétitions (0=infini, 1-255).

    Returns:
        bytes: Feature_Report de 9 octets.

    Raises:
        ValueError: Si les positions ou le count sont invalides.
    """
    validate_position(start)
    validate_position(end)
    if start >= end:
        raise ValueError(
            f"Start position must be less than end position, got start={start}, end={end}"
        )
    if not (0 <= count <= 255):
        raise ValueError(f"Count must be in 0-255, got {count}")
    return bytes(
        [REPORT_ID, CMD_PLAY_LOOP, 0x01, start, end, count, 0x00, 0x00, 0x00]
    )


def build_stop_play() -> bytes:
    """Construit le Feature_Report pour arrêter la lecture des patterns.

    Returns:
        bytes: Feature_Report de 9 octets.
    """
    return bytes(
        [REPORT_ID, CMD_PLAY_LOOP, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    )


def build_server_tickle_enable(
    timeout_ms: int, start: int, end: int
) -> bytes:
    """Construit le Feature_Report pour activer le Server Tickle (watchdog).

    Args:
        timeout_ms: Délai du watchdog en millisecondes (10-655350).
        start: Position de début du pattern à jouer (0-31, doit être < end).
        end: Position de fin du pattern à jouer (0-31, doit être > start).

    Returns:
        bytes: Feature_Report de 9 octets.

    Raises:
        ValueError: Si les paramètres sont hors de leurs bornes valides.
    """
    if not (10 <= timeout_ms <= MAX_FADE_MS):
        raise ValueError(
            f"Timeout must be in 10-{MAX_FADE_MS}ms, got {timeout_ms}"
        )
    validate_position(start)
    validate_position(end)
    if start >= end:
        raise ValueError(
            f"Start position must be less than end position, got start={start}, end={end}"
        )
    th, tl = _encode_time(timeout_ms)
    return bytes(
        [REPORT_ID, CMD_SERVER_TICKLE, 0x01, th, tl, 0x00, start, end, 0x00]
    )


def build_server_tickle_disable() -> bytes:
    """Construit le Feature_Report pour désactiver le Server Tickle.

    Returns:
        bytes: Feature_Report de 9 octets.
    """
    return bytes(
        [REPORT_ID, CMD_SERVER_TICKLE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    )


# ---------------------------------------------------------------------------
# Builders de requêtes (lecture)
# ---------------------------------------------------------------------------


def build_read_color_request(led_n: int = 0) -> bytes:
    """Construit le Feature_Report pour lire la couleur courante d'une LED.

    Args:
        led_n: Index de la LED cible (0=toutes, 1=supérieure, 2=inférieure).

    Returns:
        bytes: Feature_Report de 9 octets.

    Raises:
        ValueError: Si le LED_Index est hors de l'intervalle 0-2.
    """
    validate_led_index(led_n)
    return bytes(
        [REPORT_ID, CMD_READ_COLOR, 0x00, 0x00, 0x00, 0x00, 0x00, led_n, 0x00]
    )


def build_get_version_request() -> bytes:
    """Construit le Feature_Report pour lire la version du firmware.

    Returns:
        bytes: Feature_Report de 9 octets.
    """
    return bytes(
        [REPORT_ID, CMD_GET_VERSION, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    )


def build_read_pattern_line_request(pos: int) -> bytes:
    """Construit le Feature_Report pour lire une ligne de pattern.

    Args:
        pos: Position du pattern en mémoire (0-31).

    Returns:
        bytes: Feature_Report de 9 octets.

    Raises:
        ValueError: Si la position est hors de l'intervalle 0-31.
    """
    validate_position(pos)
    return bytes(
        [REPORT_ID, CMD_READ_PATTERN_LINE, 0x00, 0x00, 0x00, 0x00, 0x00, pos, 0x00]
    )


def build_play_state_request() -> bytes:
    """Construit le Feature_Report pour lire l'état de lecture des patterns.

    Returns:
        bytes: Feature_Report de 9 octets.
    """
    return bytes(
        [REPORT_ID, CMD_PLAY_STATE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    )


# ---------------------------------------------------------------------------
# Parsers de réponses (lecture)
# ---------------------------------------------------------------------------


def parse_read_color_response(data: bytes) -> RGBColor:
    """Parse la réponse de lecture de couleur courante.

    La réponse attendue a le marqueur de commande 'r' (0x72) en byte[1],
    et les composantes RGB en bytes[2], [3], [4].

    Args:
        data: Octets de la réponse HID (minimum 5 octets utiles).

    Returns:
        RGBColor: Couleur lue depuis le dispositif.

    Raises:
        OSError: Si le marqueur de commande en byte[1] n'est pas 0x72.
    """
    if data[1] != CMD_READ_COLOR:
        raise OSError(
            f"Invalid response marker: expected 0x{CMD_READ_COLOR:02X} ('r'), "
            f"got 0x{data[1]:02X}"
        )
    return RGBColor(r=data[2], g=data[3], b=data[4])


def parse_get_version_response(data: bytes) -> str:
    """Parse la réponse de lecture de version firmware.

    La réponse attendue a le marqueur de commande 'v' (0x76) en byte[1],
    et les octets major en byte[3] et minor en byte[4].

    Args:
        data: Octets de la réponse HID (minimum 5 octets utiles).

    Returns:
        str: Version sous forme "major.minor" en notation décimale.

    Raises:
        OSError: Si le marqueur de commande en byte[1] n'est pas 0x76.
    """
    if data[1] != CMD_GET_VERSION:
        raise OSError(
            f"Invalid response marker: expected 0x{CMD_GET_VERSION:02X} ('v'), "
            f"got 0x{data[1]:02X}"
        )
    major = data[3]
    minor = data[4]
    return f"{major}.{minor}"


def parse_read_pattern_line_response(data: bytes) -> PatternLine:
    """Parse la réponse de lecture d'une ligne de pattern.

    La réponse attendue a le marqueur de commande 'R' (0x52) en byte[1],
    les composantes RGB en bytes[2-4], et le fade time encodé en big-endian
    sur bytes[5-6] (th, tl).

    Args:
        data: Octets de la réponse HID (minimum 7 octets utiles).

    Returns:
        PatternLine: Ligne de pattern lue depuis le dispositif.

    Raises:
        OSError: Si le marqueur de commande en byte[1] n'est pas 0x52.
    """
    if data[1] != CMD_READ_PATTERN_LINE:
        raise OSError(
            f"Invalid response marker: expected 0x{CMD_READ_PATTERN_LINE:02X} ('R'), "
            f"got 0x{data[1]:02X}"
        )
    r = data[2]
    g = data[3]
    b = data[4]
    th = data[5]
    tl = data[6]
    fade_ms = (th * 256 + tl) * 10
    return PatternLine(r=r, g=g, b=b, fade_ms=fade_ms)


def parse_play_state_response(data: bytes) -> PlayState:
    """Parse la réponse de lecture de l'état de lecture des patterns.

    La réponse attendue a le marqueur de commande 'S' (0x53) en byte[1],
    l'état playing en byte[2] (0=arrêté, 1=en lecture), la position de début
    en byte[3], la position de fin en byte[4], le compteur de répétitions en
    byte[5], et la position courante en byte[6].

    Args:
        data: Octets de la réponse HID (minimum 7 octets utiles).

    Returns:
        PlayState: État de lecture des patterns.

    Raises:
        OSError: Si le marqueur de commande en byte[1] n'est pas 0x53.
    """
    if data[1] != CMD_PLAY_STATE:
        raise OSError(
            f"Invalid response marker: expected 0x{CMD_PLAY_STATE:02X} ('S'), "
            f"got 0x{data[1]:02X}"
        )
    return PlayState(
        playing=(data[2] == 1),
        play_start=data[3],
        play_end=data[4],
        play_count=data[5],
        play_pos=data[6],
    )


# ---------------------------------------------------------------------------
# Parsing/formatage de chaînes de patterns
# ---------------------------------------------------------------------------

MAX_PATTERN_SEGMENTS = 32


def parse_pattern_string(pattern_str: str) -> list[PatternLine]:
    """Parse une chaîne de pattern au format "R,G,B,fade_ms;R,G,B,fade_ms;...".

    Chaque segment est séparé par un point-virgule et contient exactement
    4 valeurs entières séparées par des virgules : R (0-255), G (0-255),
    B (0-255) et fade_ms (0-655350).

    Args:
        pattern_str: Chaîne de pattern à parser.

    Returns:
        Liste de PatternLine correspondant aux segments parsés.

    Raises:
        ValueError: Si la chaîne est vide, contient plus de 32 segments,
            ou si un segment est malformé (nombre de composantes != 4,
            valeurs non numériques, valeurs hors bornes).
    """
    if not pattern_str or pattern_str.strip() == "":
        raise ValueError(
            "Pattern string must not be empty: at least one segment is required"
        )

    segments = pattern_str.split(";")

    if len(segments) > MAX_PATTERN_SEGMENTS:
        raise ValueError(
            f"Pattern string must have at most {MAX_PATTERN_SEGMENTS} segments, "
            f"got {len(segments)}"
        )

    result: list[PatternLine] = []

    for idx, segment in enumerate(segments):
        parts = segment.split(",")

        if len(parts) != 4:
            raise ValueError(
                f"Segment {idx}: expected exactly 4 values (R,G,B,fade_ms), "
                f"got {len(parts)}"
            )

        # Parse les 4 valeurs comme entiers
        try:
            values = [int(p) for p in parts]
        except ValueError:
            raise ValueError(
                f"Segment {idx}: all values must be integers, "
                f"got '{segment}'"
            )

        r, g, b, fade_ms = values

        # Valider RGB
        out_of_range: list[str] = []
        if not (0 <= r <= MAX_RGB):
            out_of_range.append(f"r={r}")
        if not (0 <= g <= MAX_RGB):
            out_of_range.append(f"g={g}")
        if not (0 <= b <= MAX_RGB):
            out_of_range.append(f"b={b}")
        if out_of_range:
            raise ValueError(
                f"Segment {idx}: RGB values must be in 0-{MAX_RGB}, "
                f"got invalid: {', '.join(out_of_range)}"
            )

        # Valider fade_ms
        if not (0 <= fade_ms <= MAX_FADE_MS):
            raise ValueError(
                f"Segment {idx}: fade_ms must be in 0-{MAX_FADE_MS}, "
                f"got {fade_ms}"
            )

        result.append(PatternLine(r=r, g=g, b=b, fade_ms=fade_ms))

    return result


def format_pattern_lines(lines: list[PatternLine]) -> str:
    """Formate une liste de PatternLine en chaîne canonique.

    Produit une chaîne au format "R,G,B,fade_ms;R,G,B,fade_ms;..." sans
    espaces superflus.

    Args:
        lines: Liste de PatternLine à formater.

    Returns:
        Chaîne de pattern au format canonique.
    """
    return ";".join(
        f"{line.r},{line.g},{line.b},{line.fade_ms}" for line in lines
    )
