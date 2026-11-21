"""Relazioni tra atleti (PIANOLAVORO F.3): amicizie e rivalità, chimica di squadra. Funzioni pure, senza Qt e **senza RNG**.

Ogni coppia della Prima Squadra riceve, la prima volta che si incontra in un tick, un valore deterministico (crc32 degli id) che
ne fa un'amicizia, una rivalità o nulla. Il valore sta nei due atleti (`Athlete.relationships`, simmetrico) e cresce di
`RELATION_BOND_PER_RELAY` quando i due corrono nella stessa staffetta. Effetti: affiatamento della staffetta in gara
(±10) e forma di tutta la squadra (la «chimica»: amicizie meno rivalità). Non esiste un morale per atleta (Q38, opzione 1).
"""
from __future__ import annotations

import json
import zlib
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Tuple

from models.entities import (
    CHEMISTRY_FORM_MAX,
    CHEMISTRY_FORM_PER_NET_PAIR,
    RELATION_BOND_PER_RELAY,
    RELATION_FRIEND_MIN,
    RELATION_FRIEND_PCT,
    RELATION_RIVAL_MAX,
    RELATION_RIVAL_PCT,
    RELATION_STRENGTH_MAX,
    RELATION_STRENGTH_MIN,
    RELAY_FRIEND_HARMONY,
    RELAY_RIVAL_HARMONY,
    Athlete,
    GameState,
    Relay,
)


def initial_value(id_a: int, id_b: int) -> int:
    """Relazione di nascita di una coppia: 0 (nessuna), un'amicizia o una rivalità, in modo deterministico e simmetrico."""
    low, high = sorted((id_a, id_b))
    digest = zlib.crc32(f"relazione|{low}|{high}".encode())
    roll = digest % 100
    strength = RELATION_STRENGTH_MIN + (digest // 100) % (RELATION_STRENGTH_MAX - RELATION_STRENGTH_MIN + 1)
    if roll < RELATION_FRIEND_PCT:
        return strength
    if roll < RELATION_FRIEND_PCT + RELATION_RIVAL_PCT:
        return -strength
    return 0


def relation_between(a: Athlete, b: Athlete) -> int:
    return a.relationships.get(b.id, 0) if b.id is not None else 0


def is_friend(value: int) -> bool:
    return value >= RELATION_FRIEND_MIN


def is_rival(value: int) -> bool:
    return value <= RELATION_RIVAL_MAX


def set_relation(a: Athlete, b: Athlete, value: int) -> None:
    """Scrive il valore nei due atleti (simmetrico, tra −100 e +100). Anche lo zero resta scritto: dice che la coppia si è già
    «incontrata» e che il valore di nascita non va ricalcolato."""
    value = max(-100, min(100, int(value)))
    a.relationships[b.id] = value
    b.relationships[a.id] = value


def ensure_relationships(state: GameState) -> int:
    """Come `new_relationships`, ma ritorna solo quante coppie nuove ha creato (anche a valore 0: la voce a 0 dice «già incontrati»)."""
    return len(new_relationships(state))


def new_relationships(state: GameState) -> List[Tuple[Athlete, Athlete, int]]:
    """Dà una relazione a ogni coppia della Prima Squadra che non ne ha ancora una e toglie quelle verso atleti che non ci sono più.
    Una coppia già presente in uno dei due atleti non si ricalcola. Ritorna le coppie create `(a, b, valore)`, anche a valore 0
    (la voce a 0 dice «già incontrati»): servono alla notizia di una nuova amicizia o rivalità (Q38c)."""
    squad = [a for a in state.main_squad if a.id is not None]
    present = {a.id for a in state.athletes}
    for a in state.athletes:
        for other in [k for k in a.relationships if k not in present]:
            del a.relationships[other]
    created: List[Tuple[Athlete, Athlete, int]] = []
    for a, b in combinations(squad, 2):
        if b.id in a.relationships or a.id in b.relationships:
            if a.relationships.get(b.id) != b.relationships.get(a.id):  # asimmetria (vecchio dato): vince il valore di `a`
                set_relation(a, b, a.relationships.get(b.id, b.relationships.get(a.id, 0)))
            continue
        value = initial_value(a.id, b.id)
        set_relation(a, b, value)
        created.append((a, b, value))
    return created


def _pairs(members: Iterable[Athlete]) -> List[Tuple[Athlete, Athlete]]:
    return list(combinations([m for m in members if m is not None], 2))


def relay_chemistry_bonus(members: Iterable[Athlete]) -> int:
    """Affiatamento in più (o in meno) di una staffetta in gara: +10 se almeno due frazioni sono amiche, −10 se almeno due sono
    rivali; le due cose si sommano (0 se ci sono entrambe)."""
    values = [relation_between(a, b) for a, b in _pairs(members)]
    bonus = RELAY_FRIEND_HARMONY if any(is_friend(v) for v in values) else 0
    if any(is_rival(v) for v in values):
        bonus += RELAY_RIVAL_HARMONY
    return bonus


def net_pairs(state: GameState) -> int:
    """Amicizie meno rivalità tra gli atleti della Prima Squadra."""
    friends = rivals = 0
    for a, b in _pairs(state.main_squad):
        value = relation_between(a, b)
        friends += 1 if is_friend(value) else 0
        rivals += 1 if is_rival(value) else 0
    return friends - rivals


def team_chemistry_form_bonus(state: GameState) -> int:
    """Bonus (o malus) al bersaglio di forma di tutti gli atleti dovuto alla chimica di squadra, tra −3 e +3."""
    raw = round(net_pairs(state) * CHEMISTRY_FORM_PER_NET_PAIR)
    return max(-CHEMISTRY_FORM_MAX, min(CHEMISTRY_FORM_MAX, raw))


def bond_relay_teammates(
    state: GameState, relay_member_ids: Iterable[List[int]], done: Optional[set] = None
) -> int:
    """Chi ha corso insieme una staffetta si avvicina: +`RELATION_BOND_PER_RELAY` a ogni coppia di quella staffetta
    (una sola volta per coppia in un meeting, anche se corre più staffette). Ritorna quante coppie."""
    by_id = {a.id: a for a in state.athletes}
    done = set() if done is None else done  # coppie già avvicinate in questo meeting (passa lo stesso insieme a ogni staffetta)
    added = 0
    for ids in relay_member_ids:
        for ida, idb in combinations(sorted({i for i in ids if i in by_id}), 2):
            if (ida, idb) in done:
                continue
            done.add((ida, idb))
            a, b = by_id[ida], by_id[idb]
            set_relation(a, b, relation_between(a, b) + RELATION_BOND_PER_RELAY)
            added += 1
    return added


def relations_of(state: GameState, athlete: Athlete) -> List[Tuple[Athlete, int]]:
    """Le relazioni non nulle dell'atleta con atleti ancora presenti, dalla più positiva alla più negativa."""
    by_id = {a.id: a for a in state.athletes}
    rows = [(by_id[k], v) for k, v in athlete.relationships.items() if k in by_id and v != 0]
    return sorted(rows, key=lambda t: (-t[1], t[0].name))


def relation_label(value: int) -> str:
    if is_friend(value):
        return "Amicizia"
    if is_rival(value):
        return "Rivalità"
    return "Conoscenza" if value > 0 else "Attrito"


def relationships_to_json(relationships: Dict[int, int]) -> str:
    return json.dumps({str(k): int(v) for k, v in sorted(relationships.items())})


def relationships_from_json(raw: Optional[str]) -> Dict[int, int]:
    """Relazioni da una colonna JSON: voci non valide scartate, valori portati tra −100 e +100, JSON rotto = nessuna."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[int, int] = {}
    for key, value in data.items():
        try:
            out[int(key)] = max(-100, min(100, int(value)))
        except (TypeError, ValueError):
            continue
    return out
