"""Application controller mediating between GameState, SQLite persistence, and PyQt6 views."""

from __future__ import annotations

import random
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from models.database import DatabaseManager
from models.entities import (
    BANKRUPTCY_THRESHOLD,
    COACH_MAX_TIER,
    COACH_STAT_LABELS,
    COACH_STATS,
    MAX_SPECIALIZED_COACHES,
    MAX_YOUTH_COACHES,
    RELAY_CHANGE_COOLDOWN_WEEKS,
    RELAYS,
    Relay,
    coach_hire_cost,
    GYM_MAX_LEVEL,
    SCOUTING_FEES,
    SCOUTING_SEARCH_POINTS,
    STAND_EXPANSION_SEATS,
    STAND_MAX_SEATS,
    VERTICAL_SLICE_EVENTS,
    YOUTH_SQUAD_MAX,
    RaceAttitude,
    Specialty,
    Athlete,
    CompetitionSummary,
    CompetitionTier,
    EthicalDilemma,
    GameState,
    PeriodizationPhase,
    SeasonPhase,
    TrainingFocus,
    Transaction,
    gym_upgrade_cost,
    stand_expansion_cost,
)
from models.generator import (
    build_default_lineup,
    clamp_stat,
    create_initial_coaches,
    create_initial_staff,
    create_rival_clubs,
    generate_coach,
    create_season_objectives,
    generate_academy_prospects,
    generate_initial_roster,
    generate_school_scouting_pool,
    generate_vertical_slice_roster,
    get_recruitment_fee,
)
from models.simulation import (
    WeekAdvanceReport,
    advance_week,
    auto_assign_coach,
    auto_build_all_relays,
    auto_build_relay,
    promote_youth_athlete,
    upgrade_legacy_state,
)


def scouting_search_cost(points_used: int, filters: int) -> tuple[int, int]:
    """Return (points, fee) for a youth search with `filters` extra criteria this week."""
    points = SCOUTING_SEARCH_POINTS + filters
    after = min(max(SCOUTING_FEES), points_used + points)
    fee = SCOUTING_FEES[after] - SCOUTING_FEES[min(max(SCOUTING_FEES), points_used)]
    return points, fee


class GameController(QObject):
    """Coordinates user actions, simulation updates, and SQLite save/load."""

    state_changed = pyqtSignal(object)  # emits GameState
    week_advanced = pyqtSignal(object)  # emits WeekAdvanceReport
    competition_completed = pyqtSignal(object)  # emits CompetitionSummary
    dilemma_triggered = pyqtSignal(object)  # emits EthicalDilemma
    season_ended = pyqtSignal(object)  # emits SeasonEndResult
    status_message = pyqtSignal(str)

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        super().__init__()
        self.db = db_manager or DatabaseManager()
        self.rng = rng or random.Random()
        self.state: GameState = self._load_or_create_initial_state()
        # Last youth-scouting search results (transient: they leave if not signed this week)
        self.scouting_results: List[Athlete] = []

    def _load_or_create_initial_state(self) -> GameState:
        saved = self.db.load_game()
        if saved is not None:
            upgrade_legacy_state(saved, rng=self.rng)
            return saved
        return self._create_fresh_state(game_mode="vertical_slice")

    def _create_fresh_state(
        self,
        team_name: str = "Atletica Aurora",
        game_mode: str = "vertical_slice",
        province: Optional[str] = None,
    ) -> GameState:
        if game_mode == "vertical_slice":
            roster = generate_vertical_slice_roster(rng=self.rng)
            events = list(VERTICAL_SLICE_EVENTS)
            budget = 10000
            intro = (
                f"Sett. 1: Benvenuto in {team_name}! Prototipo Outdoor avviato: "
                "10 atleti, 3 discipline (100m, Lungo, 1500m) e 2 gare (Sett. 4 e Sett. 8)."
            )
        else:
            roster = generate_initial_roster(rng=self.rng)
            events = None
            budget = 18000
            intro = (
                f"Sett. 1: Carriera Completa avviata per {team_name}! "
                "Gestisci stagioni Outdoor, Cross e Indoor fino alla categoria Internazionale."
            )

        lineup = build_default_lineup(roster, event_names=events, gender="M")
        lineup_f = build_default_lineup(roster, event_names=events, gender="F")
        staff = create_initial_staff()
        coaches = create_initial_coaches(roster, rng=self.rng)
        objectives = create_season_objectives(game_mode, CompetitionTier.PROVINCIALE)

        state = GameState(
            team_name=team_name,
            game_mode=game_mode,
            budget=budget,
            week=1,
            season_number=1,
            season_phase=SeasonPhase.OUTDOOR,
            prestige=0,
            reputation=75,
            tier=CompetitionTier.PROVINCIALE,
            track_condition=82,
            member_fees_weekly=450,
            athletes=roster,
            staff=staff,
            transactions=[
                Transaction(
                    id=None,
                    week=1,
                    description="Fondo Iniziale Società",
                    category="Capitale",
                    amount=budget,
                )
            ],
            competition_history=[],
            event_lineup=lineup,
            event_lineup_f=lineup_f,
            club_records={},
            club_records_f={},
            objectives=objectives,
            milestones=[],
            news_log=[intro],
            coaches=coaches,
            rival_clubs=create_rival_clubs(rng=self.rng, province=province, team_name=team_name),
        )
        auto_build_all_relays(state)
        self.db.save_game(state)
        return state

    def start_new_game(
        self,
        team_name: str = "Atletica Aurora",
        game_mode: str = "vertical_slice",
        province: Optional[str] = None,
    ) -> None:
        """Reset to a fresh career or vertical-slice prototype and persist immediately."""
        self.state = self._create_fresh_state(
            team_name=team_name, game_mode=game_mode, province=province
        )
        self.scouting_results = []
        self.state_changed.emit(self.state)
        mode_label = "Prototipo Outdoor" if game_mode == "vertical_slice" else "Carriera Completa"
        self.status_message.emit(f"Nuova partita avviata ({mode_label}): {team_name}.")

    def save_game(self) -> None:
        self.db.save_game(self.state)
        self.status_message.emit(f"Partita salvata in {self.db.db_path.name}.")

    def load_game(self) -> bool:
        loaded = self.db.load_game()
        if loaded is None:
            self.status_message.emit("Nessun salvataggio trovato.")
            return False
        upgrade_legacy_state(loaded, rng=self.rng)
        self.state = loaded
        self.scouting_results = []
        self.state_changed.emit(self.state)
        self.status_message.emit("Salvataggio caricato.")
        return True

    def set_athlete_training(self, athlete_id: int, focus: TrainingFocus) -> None:
        for athlete in self.state.athletes:
            if athlete.id == athlete_id:
                athlete.training_focus = focus
                self.status_message.emit(f"{athlete.name}: allenamento -> {focus.value}.")
                return

    def set_athlete_periodization(
        self, athlete_id: int, phase: PeriodizationPhase
    ) -> None:
        for athlete in self.state.athletes:
            if athlete.id == athlete_id:
                athlete.periodization = phase
                self.status_message.emit(f"{athlete.name}: ciclo -> {phase.value}.")
                return

    def set_all_training(self, focus: TrainingFocus) -> None:
        for athlete in self.state.athletes:
            if not athlete.is_injured:
                athlete.training_focus = focus
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Tutti gli atleti sani assegnati a {focus.value}.")

    def set_all_periodization(self, phase: PeriodizationPhase) -> None:
        for athlete in self.state.athletes:
            if not athlete.is_injured:
                athlete.periodization = phase
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Tutti gli atleti sani impostati su {phase.value}.")

    def apply_recovery_session(self, athlete_id: int) -> bool:
        """Pay $250 for targeted physiotherapy, sleep & nutrition recovery."""
        cost = 250
        if self.state.budget < cost:
            self.status_message.emit("Budget insufficiente per la seduta di recupero ($250).")
            return False
        athlete = next((a for a in self.state.athletes if a.id == athlete_id), None)
        if athlete is None:
            return False
        self.state.budget -= cost
        athlete.fatigue = clamp_stat(athlete.fatigue - 20, 0, 100)
        athlete.sleep_quality = clamp_stat(athlete.sleep_quality + 10, 40, 100)
        athlete.nutrition = clamp_stat(athlete.nutrition + 10, 40, 100)
        athlete.form = clamp_stat(athlete.form + 6, 5, 100)
        self.state.transactions.insert(
            0,
            Transaction(
                id=None,
                week=self.state.week,
                description=f"Recupero & Nutrizione ({athlete.name})",
                category="Recupero",
                amount=-cost,
            ),
        )
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Seduta recupero completata per {athlete.name} (-20 Fatica).")
        return True

    def maintain_track(self) -> bool:
        """Spend $900 to refurbish the tartan track surface."""
        cost = 900
        if self.state.budget < cost:
            self.status_message.emit("Budget insufficiente per manutenzione pista ($900).")
            return False
        self.state.budget -= cost
        self.state.track_condition = clamp_stat(self.state.track_condition + 25, 0, 100)
        self.state.transactions.insert(
            0,
            Transaction(
                id=None,
                week=self.state.week,
                description="Manutenzione Pista in Tartan",
                category="Impianto",
                amount=-cost,
            ),
        )
        self.state.news_log.insert(
            0,
            f"Sett. {self.state.week}: Pista in tartan riqualificata ({self.state.track_condition}%).",
        )
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit("Manutenzione pista completata.")
        return True

    def toggle_staff(self, staff_id: int) -> None:
        member = next((s for s in self.state.staff if s.id == staff_id), None)
        if member is None:
            return
        member.hired = not member.hired
        action = "Assunto" if member.hired else "Licenziato"
        self.state.news_log.insert(
            0, f"Sett. {self.state.week}: {action} {member.name} ({member.role.value})."
        )
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"{action}: {member.name}.")

    def set_event_athlete(
        self, event_name: str, athlete_id: Optional[int], gender: str = "M"
    ) -> None:
        self.state.lineup_for(gender)[event_name] = athlete_id
        self.status_message.emit(f"Formazione aggiornata per {event_name} ({gender}).")

    def auto_fill_lineup(self) -> None:
        self.state.event_lineup = build_default_lineup(
            self.state.athletes, event_names=self.state.active_events, gender="M"
        )
        self.state.event_lineup_f = build_default_lineup(
            self.state.athletes, event_names=self.state.active_events, gender="F"
        )
        self.state_changed.emit(self.state)
        self.status_message.emit("Formazione ottimale completata automaticamente.")

    def generate_free_agents(self, count: int = 4) -> List[Athlete]:
        existing = {a.name for a in self.state.athletes}
        return generate_school_scouting_pool(
            tier=self.state.tier,
            count=count,
            rng=self.rng,
            existing_names=existing,
            vertical_slice_only=(self.state.game_mode == "vertical_slice"),
        )

    def recruit_athlete(self, prospect: Athlete) -> bool:
        fee = get_recruitment_fee(prospect)
        if self.state.budget < fee:
            self.status_message.emit(
                f"Fondi insufficienti per tesserare {prospect.name} (servono ${fee:,})."
            )
            return False

        next_id = max((a.id or 0 for a in self.state.athletes), default=0) + 1
        prospect.id = next_id
        self.state.athletes.append(prospect)
        auto_assign_coach(self.state, prospect)
        self.state.budget -= fee
        # Sponsors dislike squad turnover; young signings hurt fidelity less
        self.state.fidelity = max(0, self.state.fidelity - (6 if prospect.age < 21 else 12))
        tag = "Talento Studentesco" if prospect.is_youth_prospect else "Tesseramento"
        self.state.transactions.insert(
            0,
            Transaction(
                id=None,
                week=self.state.week,
                description=f"{tag}: {prospect.name} ({prospect.specialty.value})",
                category="Scouting",
                amount=-fee,
            ),
        )
        msg = (
            f"Sett. {self.state.week}: Scoperto ai Campionati Studenteschi e tesserato "
            f"{prospect.name} ({prospect.age} anni, Potenziale {prospect.potential})!"
            if prospect.is_youth_prospect
            else f"Sett. {self.state.week}: Tesserato {prospect.name} ({prospect.specialty.value})."
        )
        self.state.news_log.insert(0, msg)
        if prospect.is_youth_prospect:
            self.state.milestones.insert(0, msg)

        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Tesserato {prospect.name} per ${fee:,}.")
        return True

    def release_athlete(self, athlete_id: int) -> bool:
        target = next((a for a in self.state.athletes if a.id == athlete_id), None)
        if target is None:
            return False
        if not target.in_youth_squad and len(self.state.main_squad) <= 1:
            self.status_message.emit("Impossibile svincolare l'ultimo atleta rimasto.")
            return False
        if not target.in_youth_squad:
            self.state.fidelity = max(0, self.state.fidelity - 8)

        self.state.athletes = [a for a in self.state.athletes if a.id != athlete_id]
        self._remove_from_relays(athlete_id)
        for event_name, assigned_id in list(self.state.event_lineup.items()):
            if assigned_id == athlete_id:
                self.state.event_lineup[event_name] = None
        for event_name, assigned_id in list(self.state.event_lineup_f.items()):
            if assigned_id == athlete_id:
                self.state.event_lineup_f[event_name] = None

        self.state.news_log.insert(
            0, f"Sett. {self.state.week}: {target.name} ha lasciato la società."
        )
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Svincolato {target.name}.")
        return True

    # ------------------------------------------------------------------ race attitude
    def set_event_attitude(self, event_name: str, attitude: RaceAttitude) -> None:
        self.state.event_attitude[event_name] = attitude.value
        self.status_message.emit(f"{event_name}: atteggiamento in gara -> {attitude.value}.")

    # ------------------------------------------------------------------ youth academy
    def run_youth_scouting(
        self, specialty: Optional[Specialty] = None, high_potential: bool = False
    ) -> List[Athlete]:
        """Spend weekly scouting points (2 + 1 per filter) and money to find 1-4 kids (14-17)."""
        filters = (1 if specialty is not None else 0) + (1 if high_potential else 0)
        points, fee = scouting_search_cost(self.state.scouting_points_used, filters)
        if points > self.state.scouting_points_left:
            self.status_message.emit(
                f"Punti scouting insufficienti ({self.state.scouting_points_left} rimasti, servono {points})."
            )
            return []
        if fee > self.state.budget:
            self.status_message.emit(f"Fondi insufficienti per la ricerca (${fee:,}).")
            return []

        allowed = (
            [Specialty.SPRINTS, Specialty.JUMPS, Specialty.MIDDLE_DISTANCE]
            if self.state.game_mode == "vertical_slice"
            else None
        )
        kids = generate_academy_prospects(
            count=self.rng.randint(1, 4),
            rng=self.rng,
            specialty=specialty,
            high_potential=high_potential,
            existing_names={a.name for a in self.state.athletes},
            allowed_specialties=allowed,
        )
        self.state.scouting_points_used += points
        self.state.budget -= fee
        if fee > 0:
            self.state.transactions.insert(
                0,
                Transaction(
                    id=None,
                    week=self.state.week,
                    description=f"Osservatori vivaio ({points} punti)",
                    category="Scouting",
                    amount=-fee,
                ),
            )
        self.scouting_results = kids
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(
            f"Gli osservatori hanno segnalato {len(kids)} ragazzi (-{points} punti, -${fee:,})."
        )
        return kids

    def sign_youth(self, prospect: Athlete) -> bool:
        if len(self.state.youth_squad) >= YOUTH_SQUAD_MAX:
            self.status_message.emit(f"Vivaio pieno ({YOUTH_SQUAD_MAX} posti): promuovi o svincola qualcuno.")
            return False
        if prospect not in self.scouting_results:
            return False
        prospect.id = max((a.id or 0 for a in self.state.athletes), default=0) + 1
        prospect.in_youth_squad = True
        self.state.athletes.append(prospect)
        auto_assign_coach(self.state, prospect)
        self.scouting_results.remove(prospect)
        self.state.news_log.insert(
            0,
            f"Sett. {self.state.week}: {prospect.name} ({prospect.age} anni, {prospect.specialty.value}) "
            "entra nel vivaio.",
        )
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"{prospect.name} inserito nel vivaio.")
        return True

    def promote_youth(self, athlete_id: int) -> bool:
        athlete = next(
            (a for a in self.state.youth_squad if a.id == athlete_id), None
        )
        if athlete is None:
            return False
        promote_youth_athlete(self.state, athlete)
        msg = f"Sett. {self.state.week}: {athlete.name} promosso dal vivaio in Prima Squadra!"
        self.state.news_log.insert(0, msg)
        self.state.milestones.insert(0, msg)
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"{athlete.name} promosso (stipendio ${athlete.weekly_wage}/sett).")
        return True

    # ------------------------------------------------------------------ facilities
    def _pay(self, cost: int, description: str, category: str) -> bool:
        if self.state.budget < cost:
            self.status_message.emit(f"Budget insufficiente: servono ${cost:,}.")
            return False
        self.state.budget -= cost
        self.state.transactions.insert(
            0,
            Transaction(id=None, week=self.state.week, description=description, category=category, amount=-cost),
        )
        return True

    def upgrade_gym(self) -> bool:
        if self.state.gym_level >= GYM_MAX_LEVEL:
            self.status_message.emit("Palestra già al livello massimo.")
            return False
        cost = gym_upgrade_cost(self.state.gym_level)
        if not self._pay(cost, f"Ampliamento Palestra -> livello {self.state.gym_level + 1}", "Impianto"):
            return False
        self.state.gym_level += 1
        self.state.news_log.insert(
            0, f"Sett. {self.state.week}: Palestra ampliata al livello {self.state.gym_level}."
        )
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Palestra al livello {self.state.gym_level}.")
        return True

    def expand_stands(self) -> bool:
        if self.state.stand_seats >= STAND_MAX_SEATS:
            self.status_message.emit("Tribune già alla capienza massima.")
            return False
        cost = stand_expansion_cost(self.state.stand_seats)
        if not self._pay(cost, f"Nuove tribune (+{STAND_EXPANSION_SEATS} posti)", "Impianto"):
            return False
        self.state.stand_seats = min(STAND_MAX_SEATS, self.state.stand_seats + STAND_EXPANSION_SEATS)
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Tribune ampliate: {self.state.stand_seats:,} posti.")
        return True

    # ------------------------------------------------------------------ coaches
    def hire_coach(
        self,
        specialty: Optional[Specialty],
        primary: str,
        secondary: Optional[str],
        tier: int,
    ) -> bool:
        """Hire a coach (specialty None = youth coach). Higher tiers cost more and know more."""
        state = self.state
        if primary not in COACH_STATS or (secondary is not None and secondary not in COACH_STATS):
            return False
        tier = max(1, min(COACH_MAX_TIER, tier))
        if state.coach_hired_week == state.week:
            self.status_message.emit("Puoi assumere un solo allenatore a settimana.")
            return False
        youth = specialty is None
        count = sum(1 for c in state.coaches if c.is_youth_coach == youth)
        limit = MAX_YOUTH_COACHES if youth else MAX_SPECIALIZED_COACHES
        if count >= limit:
            kind = "del vivaio" if youth else "specializzati"
            self.status_message.emit(f"Hai già il massimo di allenatori {kind} ({limit}).")
            return False
        cost = coach_hire_cost(tier)
        if not self._pay(cost, "Ingaggio allenatore", "Allenatori"):
            return False
        coach = generate_coach(
            specialty, primary, secondary, tier, rng=self.rng,
            existing_names={c.name for c in state.coaches},
        )
        coach.id = max((c.id or 0 for c in state.coaches), default=0) + 1
        state.coaches.append(coach)
        state.coach_hired_week = state.week
        # Athletes without a suitable coach are taken on straight away
        for a in state.athletes:
            if state.coach_of(a) is None and coach.can_train(a):
                a.coach_id = coach.id
        skills = f"{COACH_STAT_LABELS[primary]} {coach.skills[primary]}"
        if secondary is not None and secondary != primary:
            skills += f", {COACH_STAT_LABELS[secondary]} {coach.skills[secondary]}"
        state.news_log.insert(
            0,
            f"Sett. {state.week}: Ingaggiato l'allenatore {coach.name} ({coach.kind_label}: {skills}).",
        )
        self.db.save_game(state)
        self.state_changed.emit(state)
        self.status_message.emit(f"Assunto {coach.name} (${coach.weekly_wage}/sett).")
        return True

    def fire_coach(self, coach_id: int) -> bool:
        coach = next((c for c in self.state.coaches if c.id == coach_id), None)
        if coach is None:
            return False
        self.state.coaches.remove(coach)
        for a in self.state.athletes:
            if a.coach_id == coach_id:
                a.coach_id = None
                auto_assign_coach(self.state, a)
        self.state.news_log.insert(
            0, f"Sett. {self.state.week}: L'allenatore {coach.name} lascia la società."
        )
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Licenziato {coach.name}.")
        return True

    def assign_coach(self, athlete_id: int, coach_id: Optional[int]) -> bool:
        athlete = next((a for a in self.state.athletes if a.id == athlete_id), None)
        if athlete is None:
            return False
        if coach_id is not None:
            coach = next((c for c in self.state.coaches if c.id == coach_id), None)
            if coach is None or not coach.can_train(athlete):
                self.status_message.emit("Questo allenatore non può seguire l'atleta.")
                return False
            athlete.coach_id = coach_id
            self.status_message.emit(f"{athlete.name} ora si allena con {coach.name}.")
        else:
            athlete.coach_id = None
            self.status_message.emit(f"{athlete.name} non ha più un allenatore.")
        self.state_changed.emit(self.state)
        return True

    # ------------------------------------------------------------------ relays
    def _remove_from_relays(self, athlete_id: int) -> None:
        for pool in (self.state.relays, self.state.relays_f):
            for relay in pool.values():
                relay.member_ids = [None if mid == athlete_id else mid for mid in relay.member_ids]
                if relay.reserve_id == athlete_id:
                    relay.reserve_id = None

    def auto_build_relay(self, event: str, gender: str = "M") -> bool:
        existing = self.state.relays_for(gender).get(event)
        weeks_since = self.state.week - (existing.last_change_week if existing else -100)
        if existing and existing.all_ids() and weeks_since < RELAY_CHANGE_COOLDOWN_WEEKS:
            self.status_message.emit(
                f"La {event} ({gender}) è stata cambiata da poco: riprova tra "
                f"{RELAY_CHANGE_COOLDOWN_WEEKS - weeks_since} settimana/e."
            )
            return False
        relay = auto_build_relay(self.state, event, gender=gender)
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.status_message.emit(f"Staffetta {event} ({gender}) composta (affiatamento {relay.harmony}).")
        return True

    def set_relay_slot(
        self, event: str, slot: int, athlete_id: Optional[int], gender: str = "M"
    ) -> bool:
        """Set leg `slot` (0-3) or the reserve (4) for the given division (`M` or `F`).

        Reordering runners already in the relay is free. Bringing in a new runner in place of
        a healthy one costs 25% harmony and is allowed once every 4 weeks.
        """
        if event not in RELAYS or gender not in ("M", "F") or not (0 <= slot <= 4):
            return False
        state = self.state
        relays = state.relays_for(gender)
        relay = relays.setdefault(event, Relay(event=event))
        slots: List[Optional[int]] = list(relay.member_ids) + [relay.reserve_id]
        current = slots[slot]
        if athlete_id == current:
            return True

        if athlete_id is not None:
            athlete = next((a for a in state.main_squad if a.id == athlete_id), None)
            if athlete is None or athlete.gender != gender:
                return False
            other = state.relay_of(athlete_id, gender=gender)
            if other is not None and other != event:
                self.status_message.emit(f"{athlete.name} corre già nella staffetta {other} ({gender}).")
                return False

        if athlete_id is not None and athlete_id in slots:
            # Reorder within the team: swap places, no penalty
            j = slots.index(athlete_id)
            slots[slot], slots[j] = slots[j], slots[slot]
        else:
            by_id = {a.id: a for a in state.main_squad}
            outgoing = by_id.get(current) if current is not None else None
            is_replacement = outgoing is not None and not outgoing.is_injured
            if is_replacement:
                weeks_since = state.week - relay.last_change_week
                if weeks_since < RELAY_CHANGE_COOLDOWN_WEEKS:
                    self.status_message.emit(
                        f"Puoi cambiare un componente della {event} ({gender}) tra "
                        f"{RELAY_CHANGE_COOLDOWN_WEEKS - weeks_since} settimana/e."
                    )
                    return False
                relay.harmony = int(relay.harmony * 0.75)
                relay.last_change_week = state.week
            slots[slot] = athlete_id
        relay.member_ids = slots[:4]
        relay.reserve_id = slots[4]
        self.db.save_game(state)
        self.state_changed.emit(state)
        self.status_message.emit(f"Staffetta {event} ({gender}) aggiornata (affiatamento {relay.harmony}).")
        return True

    def resolve_dilemma(self, accepted: bool) -> None:
        """Apply the player's moral decision to the pending ethical dilemma."""
        dilemma = self.state.pending_dilemma
        if dilemma is None:
            return

        athlete = next(
            (a for a in self.state.athletes if a.id == dilemma.athlete_id), None
        )
        if dilemma.id.startswith("doping"):
            if accepted:
                self.state.budget += 1800
                self.state.reputation = clamp_stat(self.state.reputation - 18, 0, 100)
                if athlete is not None:
                    athlete.doping_boost_weeks = 3
                    athlete.form = clamp_stat(athlete.form + 14, 5, 100)
                self.state.transactions.insert(
                    0,
                    Transaction(
                        id=None,
                        week=self.state.week,
                        description="Sponsor 'Integratori Sperimentali'",
                        category="Sponsor",
                        amount=1800,
                    ),
                )
                self.state.news_log.insert(
                    0,
                    f"Sett. {self.state.week}: Accettata la scorciatoia dello sponsor. Prestazioni su, ma rischio squalifica alto!",
                )
            else:
                self.state.budget = max(0, self.state.budget - 600)
                self.state.reputation = clamp_stat(self.state.reputation + 10, 0, 100)
                self.state.prestige += 8
                self.state.news_log.insert(
                    0,
                    f"Sett. {self.state.week}: Rifiutata ogni scorciatoia farmacologica! Reputazione del club salita a {self.state.reputation}%.",
                )
        else:  # youth push dilemma
            if accepted:
                self.state.budget += 1000
                if athlete is not None:
                    athlete.fatigue = clamp_stat(athlete.fatigue + 22, 0, 100)
                self.state.transactions.insert(
                    0,
                    Transaction(
                        id=None,
                        week=self.state.week,
                        description="Evento Promozionale Sponsor",
                        category="Sponsor",
                        amount=1000,
                    ),
                )
                self.state.news_log.insert(
                    0,
                    f"Sett. {self.state.week}: Sforzo extra per lo sponsor (+$1.000, fatica aumentata).",
                )
            else:
                self.state.budget = max(0, self.state.budget - 300)
                if athlete is not None:
                    athlete.resilience = clamp_stat(athlete.resilience + 6, 1, 100)
                    athlete.form = clamp_stat(athlete.form + 8, 5, 100)
                self.state.news_log.insert(
                    0,
                    f"Sett. {self.state.week}: Protetta la crescita dell'atleta (+Resilienza & Forma).",
                )

        self.state.pending_dilemma = None
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)

    def advance_week(self) -> Optional[WeekAdvanceReport]:
        if self.state.bankrupt:
            self.status_message.emit(
                f"Società fallita (debito oltre ${-BANKRUPTCY_THRESHOLD:,}): avvia una nuova partita."
            )
            return None
        report = advance_week(self.state, rng=self.rng)
        self.scouting_results = []
        self.db.save_game(self.state)
        self.state_changed.emit(self.state)
        self.week_advanced.emit(report)

        if report.competition_summary is not None:
            self.competition_completed.emit(report.competition_summary)
            self.status_message.emit(
                f"Gara Sett. {report.completed_week} completata! "
                f"+${report.competition_summary.total_prize_money:,} | "
                f"+{report.competition_summary.total_prestige_gained} Prestigio"
            )
        else:
            self.status_message.emit(f"Avanzato alla Settimana {report.new_week}.")

        if report.season_end is not None:
            self.season_ended.emit(report.season_end)

        if report.triggered_dilemma is not None:
            self.dilemma_triggered.emit(report.triggered_dilemma)

        return report
