"""Formazione del gruppo nelle gare con rientro alla corda (800m, 1500m): chi sta dove, di lato, in ogni istante. Senza Qt e senza RNG.

**Solo messa in scena** (PIANOLAVORO G): non tocca tempi, ordine né misure; decide soltanto la posizione laterale di ogni corridore sulla pista.
Regole (come in gara vera):
- fino alla **linea di rientro** (800m: fine della prima curva, π·R1 ≈ 115,6 m; 1500m: subito) si resta nella propria corsia;
- dopo, tutti puntano alla **corda** (lato stretto della curva). A passi di `STEP` secondi ognuno prende la fila più interna in cui nessuno gli sta troppo vicino
  (davanti entro `GAP_AHEAD`, dietro entro `GAP_BEHIND`). Si va in ordine di fila attuale (chi è già dentro ha la precedenza: **isteresi**), poi dal più avanzato:
  chi sta superando passa all'esterno e rientra solo quando ha lasciato `GAP_BEHIND` metri, **senza spingere fuori chi viene superato**;
- la posizione laterale è la **media delle file su una finestra di tempo** (`WINDOW`): niente scatti;
- **distanza minima**: due corridori a fianco (a meno di `SEP_ALONG` metri lungo la pista) restano ad almeno `SEP_LAT` di lato; chi ha la precedenza più alta
  (la corsia di partenza, o l'ordine d'uscita per chi si ferma) viene spinto fuori quanto basta. La spinta si **anticipa e si addolcisce** (`PUSH_HALF`, `AVG_HALF`):
  senza, due che si sfiorano a grande velocità relativa (l'arrivo in gruppo) producevano scatti laterali di 6 m/s;
- chi **si ferma** (ritirato, oppure arrivato che ha tagliato il traguardo) non occupa più la corda: si sposta verso l'esterno in `LEAVE_SECONDS`, ognuno in una
  fila diversa (`assign_exit_lats`: il primo a fermarsi è il più esterno). Senza questo, chi arriva ultimo attraversava il gruppo già rallentato.

È una funzione pura del tempo di gara (ralenti: si riavvolge e si rilegge): l'isteresi si calcola a passi dalla partenza e il risultato si tiene in cache,
che è solo un'ottimizzazione. Questo modulo è il **riferimento**: `godot_viewer/models/PackFormation.gd` è la sua trascrizione (stesse costanti, stesso algoritmo)
e `views/race_3d.py` lo usa direttamente. Se cambi qualcosa qui, cambialo anche lì (c'è un test di parità con valori fissi).
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

SLOT_W = 0.95  # m tra due file affiancate (spalla a spalla)
MAX_SLOT = 7  # file massime (7 · 0,95 = 6,65 m dalla corda: dentro le 8 corsie)
GAP_AHEAD = 1.6  # m: chi ha qualcuno davanti più vicino di così non può stare nella stessa fila
GAP_BEHIND = 3.0  # m: chi ha qualcuno dietro più vicino di così non può rientrare nella sua fila (si lascia spazio prima di tagliare)
STEP = 0.2  # s: passo di calcolo delle file
WINDOW_STEPS = 10  # passi nella finestra della media (10 · 0,2 = 2 s): addolcisce i cambi di fila
SEP_LAT = 0.75  # m: distanza laterale minima fra due corridori a fianco (spalla a spalla)
SEP_ALONG = 2.4  # m: oltre questa distanza lungo la pista due corridori non si ostacolano (in fila); più largo = correzione più dolce
SEP_FULL = 0.5  # m: sotto questa distanza lungo la pista la separazione laterale è piena
SEP_PASSES = 3  # ripetizioni della verifica (una correzione può avvicinare un altro corridore)
PUSH_HALF = 3  # la spinta richiesta si estende di ±3 passi (±0,6 s): ci si sposta PRIMA di incontrarsi e si resta spostati un attimo dopo...
AVG_HALF = 3  # ...e poi si addolcisce con una media di ±3 passi: la spinta non scatta (picco ≤ spinta / 1,2 s) ma resta sempre almeno quella richiesta
OUTER_LAT = 7.6  # m dalla corda: dove va il primo a fermarsi (ritirato o arrivato)
EXIT_STEP = 0.9  # m: ogni corridore che si ferma dopo si ferma un po' più dentro del precedente (nessuno si sovrappone)
EXIT_MIN = 0.9  # m: la fila più interna in cui ci si ferma
LEAVE_SECONDS = 5.0  # s per spostarsi all'esterno dopo l'arresto (picco ~2,3 m/s per 7,6 m)

# (inizio, fine) del rientro alla corda, in metri dalla partenza. 800m: fine della prima curva = π·R1 (R1 = 36,8 m) = 115,6 m.
BREAK_WINDOWS: Dict[str, Tuple[float, float]] = {"800m": (115.6, 145.0), "1500m": (10.0, 90.0)}

DistFn = Callable[[int, float], float]  # (corridore, tempo di gara) → metri dalla sua partenza


def applies_to(kind: str) -> bool:
    return kind in BREAK_WINDOWS


def smoothstep(a: float, b: float, x: float) -> float:
    if b <= a:
        return 1.0 if x >= a else 0.0
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def assign_slots(dists: Sequence[float], prev_lats: Sequence[float], start_lats: Sequence[float], present: Sequence[bool]) -> List[int]:
    """Le file (0 = corda) di ogni corridore presente al passo successivo. Ordine: posizione laterale **fisica** del passo prima (chi è più dentro tiene il posto:
    isteresi; uno che sta ancora rientrando non occupa la corda finché non ci arriva), poi più avanti, poi corsia interna. Un assente (ritirato fermo): -1."""
    n = len(dists)
    order = sorted((i for i in range(n) if present[i]), key=lambda i: (prev_lats[i], -dists[i], start_lats[i], i))
    slots = [-1] * n
    placed: List[int] = []
    for i in order:
        chosen = MAX_SLOT
        for s in range(MAX_SLOT + 1):
            if all(not (slots[k] == s and -GAP_BEHIND < dists[k] - dists[i] < GAP_AHEAD) for k in placed):
                chosen = s
                break
        slots[i] = chosen
        placed.append(i)
    return slots


def assign_exit_lats(stop_times: Sequence[Optional[float]]) -> List[float]:
    """Dove si ferma ognuno di quelli che si fermano: per ordine di arresto (a parità, per indice), dal più esterno verso l'interno."""
    order = sorted((i for i, st in enumerate(stop_times) if st is not None), key=lambda i: (stop_times[i], i))
    out = [OUTER_LAT] * len(stop_times)
    for k, i in enumerate(order):
        out[i] = max(EXIT_MIN, OUTER_LAT - EXIT_STEP * k)
    return out


class PackFormation:
    """La formazione del gruppo di una gara. `start_lats[i]`: scostamento della corsia di partenza dalla corda (m); `dist_fn(i, t)`: metri percorsi;
    `stop_times[i]`: istante in cui si ferma (ritirato, o arrivato che ha tagliato il traguardo; None = ancora in corsa). `dist_fn` e `stop_times` non devono cambiare durante la gara."""

    def __init__(self, kind: str, start_lats: Sequence[float], dist_fn: DistFn, stop_times: Optional[Sequence[Optional[float]]] = None) -> None:
        self.kind = kind
        self.n = len(start_lats)
        self.start_lats = list(start_lats)
        self.dist_fn = dist_fn
        self.stops: List[Optional[float]] = list(stop_times) if stop_times is not None else [None] * self.n
        self.exit_lats = assign_exit_lats(self.stops)
        stoppers = sorted((i for i in range(self.n) if self.stops[i] is not None), key=lambda i: (self.stops[i], i))
        self._exit_order = {i: k for k, i in enumerate(stoppers)}  # 0 = il primo a fermarsi
        self._hist: List[List[int]] = []  # file a ogni passo (cache: si può riempire solo in avanti)
        self._phys: List[List[float]] = []  # posizione laterale fisica a ogni passo (prima della verifica di distanza minima)
        self._push: List[List[float]] = []  # spinta di distanza minima richiesta a ogni passo
        # ultimo passo in cui il corridore è presente (chi si ferma non conta più dopo): la finestra della media non deve contare i passi da assente
        self._last_present = [
            (int(math.ceil(st / STEP)) - 1 if st is not None else 10**9) for st in self.stops
        ]
        order = sorted(range(self.n), key=lambda i: (self.start_lats[i], i))
        self._lane_rank = [order.index(i) for i in range(self.n)]  # 0 = corsia più interna

    def _present(self, i: int, t: float) -> bool:
        return self.stops[i] is None or t < self.stops[i]

    def _slots_at_step(self, k: int) -> List[int]:
        while len(self._hist) <= k:
            j = len(self._hist)
            t = j * STEP
            dists = [self.dist_fn(i, t) for i in range(self.n)]
            present = [self._present(i, t) for i in range(self.n)]
            prev = self.start_lats if j == 0 else self._phys[j - 1]  # precedenza: chi è fisicamente più dentro
            self._hist.append(assign_slots(dists, prev, self.start_lats, present))
            self._phys.append([self._lat(i, t) for i in range(self.n)])  # usa le file fino a questo passo (la finestra guarda indietro)
        return self._hist[k]

    def _averaged_slot_lat(self, i: int, step_pos: float) -> float:
        """Fila media (in metri dalla corda) nella finestra che finisce al passo `step_pos` (frazionario: interpolazione fra due passi)."""
        k0 = int(step_pos)
        frac = step_pos - k0

        def avg(k: int) -> float:
            total = 0.0
            for j in range(WINDOW_STEPS):
                kk = min(max(0, k - j), max(0, self._last_present[i]))
                s = self._slots_at_step(kk)[i]
                total += (s if s >= 0 else MAX_SLOT) * SLOT_W
            return total / WINDOW_STEPS

        return avg(k0) if frac <= 1e-12 else avg(k0) * (1.0 - frac) + avg(k0 + 1) * frac

    def _lat(self, i: int, t: float) -> float:
        a, b = BREAK_WINDOWS[self.kind]
        w = smoothstep(a, b, self.dist_fn(i, t))
        if w <= 0.0:
            return self.start_lats[i]  # prima della linea di rientro: nella propria corsia, esattamente
        slot_lat = self._averaged_slot_lat(i, t / STEP)
        return self.start_lats[i] + (slot_lat - self.start_lats[i]) * w

    def _base(self, t: float) -> List[float]:
        """Posizioni laterali prima della verifica di distanza minima: file mediate, rientro e uscita di chi si ferma."""
        out: List[float] = []
        for i in range(self.n):
            stop = self.stops[i]
            if stop is not None and t >= stop:
                at_stop = self._lat(i, stop - 1e-3)  # appena prima dell'arresto: ancora presente
                out.append(at_stop + (self.exit_lats[i] - at_stop) * smoothstep(0.0, LEAVE_SECONDS, t - stop))
            else:
                out.append(self._lat(i, t))
        return out

    def _grid_push(self, k: int) -> List[float]:
        """Spinta di distanza minima richiesta al passo `k` (≥ 0 per ognuno), in cache."""
        while len(self._push) <= k:
            j = len(self._push)
            t = j * STEP
            base = self._base(t)
            sep = self._separate(base, t)
            self._push.append([sep[i] - base[i] for i in range(self.n)])
        return self._push[k]

    def _grid_env(self, k: int) -> List[float]:
        """Spinta estesa nel tempo: il massimo della richiesta entro ±`PUSH_HALF` passi (si anticipa e si trattiene)."""
        out = [0.0] * self.n
        for m in range(-PUSH_HALF, PUSH_HALF + 1):
            row = self._grid_push(max(0, k + m))
            for i in range(self.n):
                out[i] = max(out[i], row[i])
        return out

    def _grid_avg(self, k: int) -> List[float]:
        """Spinta addolcita: media dell'estesa entro ±`AVG_HALF` passi. Resta ≥ della richiesta nell'istante (l'estesa la copre per tutta la finestra)."""
        out = [0.0] * self.n
        count = 2 * AVG_HALF + 1
        for m in range(-AVG_HALF, AVG_HALF + 1):
            row = self._grid_env(max(0, k + m))
            for i in range(self.n):
                out[i] += row[i] / count
        return out

    def lateral_offsets(self, t: float) -> List[float]:
        """Posizione laterale (m dalla corda, ≥ 0) di ogni corridore al tempo di gara `t`. Per le gare senza rientro: le corsie di partenza."""
        if not applies_to(self.kind):
            return list(self.start_lats)
        t = max(0.0, t)
        base = self._base(t)
        pos = t / STEP
        k0 = int(pos)
        frac = pos - k0
        a0 = self._grid_avg(k0)
        if frac <= 1e-12:
            return [base[i] + a0[i] for i in range(self.n)]
        a1 = self._grid_avg(k0 + 1)
        return [base[i] + a0[i] * (1.0 - frac) + a1[i] * frac for i in range(self.n)]

    def _priority(self, i: int, t: float) -> float:
        """Chi ha la chiave più alta sta più fuori quando due si sfiorano: la corsia di partenza (statica: nessun salto), e per chi si ferma una chiave che sale
        gradualmente (in `LEAVE_SECONDS`) oltre quella di tutti quelli in corsa, il primo a fermarsi più in alto."""
        stop = self.stops[i]
        key = float(self._lane_rank[i])
        if stop is not None and t > stop:
            w = smoothstep(0.0, LEAVE_SECONDS, t - stop)
            key = key * (1.0 - w) + (2.0 * self.n - self._exit_order[i]) * w  # a transizione completata conta solo l'ordine d'uscita
        return key

    def _separate(self, lats: List[float], t: float) -> List[float]:
        """Distanza minima fra due corridori a fianco. Chi ha la chiave di precedenza più alta (`_priority`) si sposta fuori."""
        d = [self.dist_fn(i, t) for i in range(self.n)]
        keys = [self._priority(i, t) for i in range(self.n)]
        out = list(lats)
        for _ in range(SEP_PASSES):
            for i in range(self.n):
                for j in range(i + 1, self.n):
                    along = abs(d[i] - d[j])
                    if along >= SEP_ALONG:
                        continue
                    inner, outer = (i, j) if (keys[i], i) < (keys[j], j) else (j, i)
                    need = SEP_LAT - (out[outer] - out[inner])
                    if need > 0.0:
                        out[outer] += need * (1.0 - smoothstep(SEP_FULL, SEP_ALONG, along))
        return out
