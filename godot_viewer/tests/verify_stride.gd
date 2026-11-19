extends SceneTree
## Verifica headless di StrideModel (cadenza e ampiezza di passo) contro le fasce di raw/parametri_biomeccanici_atletica.md:
##   godot --headless --path godot_viewer -s res://tests/verify_stride.gd
## Le velocita' vengono da RaceMotion (la stessa curva che muove i corridori). Esce con codice 0 se tutto torna, 1 altrimenti.

var _failures: int = 0


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


## (distanza, velocita') di un corridore con quel tempo ufficiale al punto di gara `at_m` metri dalla partenza.
func _speed_at(kind: String, final_time: float, at_m: float) -> float:
	var reaction: float = 0.15
	var t: float = reaction
	while t < final_time + 1.0:
		var st: Vector2 = RaceMotion.state_at(t, reaction, final_time, kind)
		if st.x >= at_m:
			return st.y
		t += 0.01
	return 0.0


func _process(_delta: float) -> bool:
	var h: float = StrideModel.REF_HEIGHT

	# --- cadenza per evento e fase (Hz)
	var peak: float = 0.0
	for i in range(0, 101):
		peak = maxf(peak, StrideModel.cadence("100m", float(i), h))
	_check(peak >= 4.6 and peak <= 5.0, "100m: picco di cadenza %.2f Hz entro 4,6-5,0" % peak)
	var ok_cruise: bool = true
	for d in range(30, 81, 5):
		var f: float = StrideModel.cadence("100m", float(d), h)
		ok_cruise = ok_cruise and f >= 4.4 and f <= 4.7
	_check(ok_cruise, "100m: fase lanciata 30-80 m fra 4,4 e 4,7 Hz")
	_check(StrideModel.cadence("100m", 0.0, h) < StrideModel.cadence("100m", 25.0, h) - 0.8, "100m: la frequenza sale nei primi 25 m")
	var drop: float = 1.0 - StrideModel.cadence("100m", 100.0, h) / StrideModel.cadence("100m", 80.0, h)
	_check(drop >= 0.03 and drop <= 0.05, "100m: cala del %.1f%% fra 80 e 100 m (3-5%%)" % (drop * 100.0))

	var first_200: bool = true
	for d in range(30, 201, 10):
		var f4: float = StrideModel.cadence("400m", float(d), h)
		first_200 = first_200 and f4 >= 3.8 and f4 <= 4.0
	_check(first_200, "400m: primi 200 m fra 3,8 e 4,0 Hz")
	_check(StrideModel.cadence("400m", 399.0, h) < 3.5, "400m: ultimo rettilineo sotto 3,5 Hz (%.2f)" % StrideModel.cadence("400m", 399.0, h))
	var falling: bool = true
	for d in range(200, 400, 10):
		falling = falling and StrideModel.cadence("400m", float(d + 10), h) <= StrideModel.cadence("400m", float(d), h) + 1e-9
	_check(falling, "400m: dopo i 200 m la cadenza non risale (fatica)")

	var mid_ok: bool = true
	for d in range(100, 1200, 100):
		var f15: float = StrideModel.cadence("1500m", float(d), h)
		mid_ok = mid_ok and f15 >= 3.1 and f15 <= 3.3
	_check(mid_ok, "1500m: gran parte della gara fra 3,1 e 3,3 Hz")
	var kick: float = StrideModel.cadence("1500m", 1499.0, h)
	_check(kick >= 3.7 and kick <= 4.0, "1500m: volata finale %.2f Hz (3,7-4,0)" % kick)
	_check(StrideModel.cadence("1500m", 1350.0, h) > StrideModel.cadence("1500m", 1250.0, h), "1500m: la cadenza sale negli ultimi 300 m")

	# --- altezza: -4/-6% fra 1,75 e 1,92 m
	var ratio: float = StrideModel.cadence("100m", 50.0, 1.92) / StrideModel.cadence("100m", 50.0, 1.75)
	_check(ratio >= 0.94 and ratio <= 0.96, "altezza: 1,92 m ha il %.1f%% di cadenza in meno di 1,75 m (4-6%%)" % ((1.0 - ratio) * 100.0))
	var v: float = 10.5
	_check(StrideModel.step_length("100m", 50.0, v, 1.92) > StrideModel.step_length("100m", 50.0, v, 1.75),
		"altezza: a pari velocita' l'atleta piu' alto ha il passo piu' lungo")

	# --- ampiezza di passo con le velocita' reali di RaceMotion (atleti di livello)
	var l100: bool = true
	for d in range(40, 91, 10):
		var s100: float = _speed_at("100m", 9.9, float(d))
		var l: float = StrideModel.step_length("100m", float(d), s100, h)
		l100 = l100 and l >= 2.2 and l <= 2.6
	_check(l100, "100m (9,90 s): ampiezza 40-90 m fra 2,20 e 2,60 m")
	_check(is_equal_approx(StrideModel.step_length("100m", 0.0, 0.0, h), StrideModel.START_STEP_LENGTH), "100m: il primo passo e' lungo 1,10 m (non si pedala sul posto)")
	_check(StrideModel.step_length("100m", 30.0, _speed_at("100m", 9.9, 30.0), h) >= 2.3, "100m: a 30 m l'ampiezza ha raggiunto 2,30 m")
	var l400: bool = true
	for d in range(60, 191, 20):
		var l4: float = StrideModel.step_length("400m", float(d), _speed_at("400m", 49.0, float(d)), h)
		l400 = l400 and l4 >= 2.0 and l4 <= 2.35
	_check(l400, "400m (49,00 s): ampiezza nei primi 200 m fra 2,00 e 2,35 m")
	var l1500: bool = true
	for d in range(200, 1100, 200):
		var l15: float = StrideModel.step_length("1500m", float(d), _speed_at("1500m", 240.0, float(d)), h)
		l1500 = l1500 and l15 >= 1.75 and l15 <= 2.10
	_check(l1500, "1500m (4:00): ampiezza fra 1,75 e 2,10 m")

	# --- v = f x L in regime, staffette e concorsi
	var sp: float = 11.0
	_check(is_equal_approx(StrideModel.cadence("100m", 60.0, h) * StrideModel.step_length("100m", 60.0, sp, h), sp), "v = f x L a 60 m dei 100m")
	_check(is_equal_approx(StrideModel.cycle_length("100m", 60.0, sp, h), 2.0 * StrideModel.step_length("100m", 60.0, sp, h)), "ciclo = 2 passi")
	_check(StrideModel.cadence("4x100m", 40.0, h) == StrideModel.cadence("100m", 40.0, h), "4x100m usa la curva dei 100m")
	_check(StrideModel.cadence("4x400m", 150.0, h) == StrideModel.cadence("400m", 150.0, h), "4x400m usa la curva dei 400m")
	_check(not StrideModel.is_supported("Salto in Lungo") and StrideModel.cadence("Salto in Lungo", 5.0) == 0.0, "i concorsi non hanno curva di cadenza")

	print("RISULTATO: " + ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true
