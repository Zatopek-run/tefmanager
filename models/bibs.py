"""Numeri di pettorale: uno per atleta per meeting, assegnato qui e solo qui.

Come nei meeting veri il numero lo assegna l'organizzazione all'iscrizione: vale per tutto il meeting (lo stesso atleta lo porta
in ogni gara, concorsi compresi), è unico fra tutti i partecipanti, a tre cifre, e non dipende dall'ordine d'arrivo. Una staffetta
ha un solo numero, portato da tutte le frazioni. Sorteggio deterministico dal meeting: rivedendo la gara i numeri sono gli stessi.

Non è un campo salvato dell'atleta: ``EventStanding`` non porta un id, quindi la chiave è ``(squadra, nome)``. Se un giorno il numero
dovesse essere un attributo persistente (con migrazione del salvataggio), basta cambiare ``assign_bibs``: viste ed esportazione
lo chiamano soltanto. Niente import dalle viste: lo usano sia ``models.race_export`` sia ``views.results_board``.
"""

from __future__ import annotations

import random
import zlib
from typing import Dict, Tuple

from models.entities import CompetitionSummary, EventStanding

BIB_MIN = 100
BIB_MAX = 999  # estremo incluso: 900 numeri a tre cifre

BibKey = Tuple[str, str]  # (squadra, nome): due atleti omonimi di squadre diverse sono persone diverse


def bib_key(standing: EventStanding) -> BibKey:
    return (standing.team_name, standing.athlete_name)


def meeting_seed(summary: CompetitionSummary) -> str:
    """Stesso seed di ``models.race_export.race_seed`` e della vista PyQt: la stessa gara si rivede uguale."""
    return f"{summary.week}-{summary.meet_name}"


def assign_bibs(summary: CompetitionSummary) -> Dict[BibKey, int]:
    """Numero di pettorale di ogni partecipante del meeting (squadre di staffetta comprese), unici e a tre cifre."""
    keys = sorted({bib_key(s) for result in summary.event_results for s in result.standings})
    if len(keys) > BIB_MAX - BIB_MIN + 1:
        raise ValueError(f"{len(keys)} partecipanti: più dei {BIB_MAX - BIB_MIN + 1} numeri a tre cifre.")
    rng = random.Random(zlib.crc32(f"{meeting_seed(summary)}|bibs".encode()))
    numbers = rng.sample(range(BIB_MIN, BIB_MAX + 1), len(keys))
    return dict(zip(keys, numbers))


def bib_of(bibs: Dict[BibKey, int], standing: EventStanding) -> int:
    """Il numero di un partecipante, 0 se non c'è (nessun pettorale da mostrare)."""
    return bibs.get(bib_key(standing), 0)
