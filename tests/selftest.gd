extends Node
## Fast checks that need no rendering: pure logic, data integrity and asset presence.
##
##   godot --headless --path <project> -- --selftest
##
## Why this exists alongside tests/shot.gd
## ---------------------------------------
## shot.gd is the real verification: it plays a whole run and is the only thing that can catch
## "the loop stopped working". But it opens a window, renders 1080p frames and takes about a
## minute, which makes it the wrong tool for the question "is this build fundamentally sane" —
## asked before every export.
##
## So this is the cheap layer underneath it: generator invariants over many seeds, the data
## tables that the loop depends on, and whether every asset the code names is actually present.
## A missing asset is exactly the kind of thing that survives a code review and fails on a
## player's machine, because every prop has a box fallback and the game keeps running without it.

const House := preload("res://scripts/game/chapter_house.gd")
const Run := preload("res://scripts/game/run.gd")

var failures: Array[String] = []
var checks := 0


func _ready() -> void:
	print("--- Iron Vigil self-test ---")
	_generator()
	_assets()
	_constants()
	if failures.is_empty():
		print("\nSELFTEST OK (%d checks)" % checks)
		get_tree().quit(0)
	else:
		push_error("\nSELFTEST FAILED (%d checks):\n  - %s" % [checks, "\n  - ".join(failures)])
		get_tree().quit(1)


func _check(ok: bool, what: String) -> void:
	checks += 1
	if not ok:
		failures.append(what)


func _generator() -> void:
	## The generator is the only thing standing between the player and an unwinnable run, so it
	## is checked over many seeds rather than the one or two a screenshot happens to use. A layout
	## that is disconnected once in fifty seeds is a bug a playtest will find and a unit test will
	## not, and the game is 15 minutes long.
	print("generator over 200 seeds...")
	var relics_ok := 0
	var altar_ok := 0
	var connected := 0
	for seed_value in range(1, 201):
		var h := House.new()
		h.generate(8, seed_value)
		if h.all_rooms_reachable():
			connected += 1
		if h.rooms.size() == 8:
			pass
		var relic_chests := 0
		var altars := 0
		for cell in h.rooms:
			for c in h.rooms[cell].chests:
				if str(c["loot"]).begins_with("relic_"):
					relic_chests += 1
			if h.rooms[cell].has_altar:
				altars += 1
		if relic_chests == 2:
			relics_ok += 1
		if altars == 1:
			altar_ok += 1
	_check(connected == 200, "every seed generates a connected house (%d/200)" % connected)
	_check(relics_ok == 200, "every seed places exactly 2 relic chests (%d/200)" % relics_ok)
	_check(altar_ok == 200, "every seed places exactly 1 altar (%d/200)" % altar_ok)

	# The relics must be reachable, which is a different question from "the graph is connected":
	# a relic chest placed in a room with no door would satisfy the count and still be unwinnable.
	var reachable_relics := 0
	for seed_value in range(1, 201):
		var h2 := House.new()
		h2.generate(8, seed_value)
		var depths: Dictionary = h2._depths(h2.entrance)
		var found := 0
		for cell in h2.relic_rooms:
			if depths.has(cell):
				found += 1
		if found == 2:
			reachable_relics += 1
	_check(reachable_relics == 200,
		"both relic rooms are reachable on every seed (%d/200)" % reachable_relics)


func _assets() -> void:
	## Every asset the code names, checked by path. A missing one does not crash — every prop
	## falls back to a box — which is exactly why it needs a test: the game would ship looking
	## wrong and nothing would say so.
	print("assets...")
	var required := [
		# figures
		"res://assets/characters/knight_walk/knight_walk.png",
		"res://assets/characters/knight/knight.png",
		"res://assets/enemies/cultist/cultist.png",
		# tiles: only the ones the generator can actually hand out. floor_wood and floor_cloth
		# are declared as wanted-but-not-drawn in chapter_house.gd, so they are not required here
		# — requiring them would fail the build for a gap that is already handled and visible.
		"res://assets/tiles/floor_stone.png",
		"res://assets/tiles/wall_stone.png",
		# props the game builds by name
		"res://assets/props/door_closed.png",
		"res://assets/props/door_open.png",
		"res://assets/props/chest_closed.png",
		"res://assets/props/chest_open.png",
		"res://assets/props/altar.png",
		"res://assets/props/altar_lit.png",
		"res://assets/props/candle_rack.png",
		"res://assets/props/pillar.png",
		"res://assets/props/banner.png",
		"res://assets/props/sigil.png",
	]
	var missing: Array = []
	for p in required:
		if not ResourceLoader.exists(p):
			missing.append(p.get_file())
	_check(missing.is_empty(), "assets present (missing: %s)" % ", ".join(missing))

	## Sound is checked separately and loudly, because a missing clip is silent: the game plays
	## nothing, says nothing, and the audio design quietly stops existing.
	var clips := [
		"foot_stone", "foot_wood", "foot_cloth", "foot_run",
		"stone_throw", "stone_impact",
		"door_open_soft", "door_open_hard", "door_slam",
		"chest_open", "pickup", "relic_pickup", "altar_lit", "altar_refuse",
		"swing", "hit_flesh", "enemy_die", "player_hurt",
		"cultist_chant", "cultist_alert", "cultist_die",
		"house_groan", "drip", "heartbeat",
		"amb_house", "amb_tension",
	]
	var missing_audio: Array = []
	for c in clips:
		if not ResourceLoader.exists("res://assets/sfx/%s.wav" % c):
			missing_audio.append(c)
	_check(missing_audio.is_empty(),
		"all %d sound clips present (missing: %s)" % [clips.size(), ", ".join(missing_audio)])

	## Every floor theme the generator can hand out must have BOTH art and a footstep clip. This
	## is the check that found floor_wood and floor_cloth being generated with no tile: the room
	## silently fell back to the procedural floor, so one room in eight looked hand-drawn and
	## nothing reported it.
	var themes_ok: Array = []
	for theme in _generated_themes():
		if not ResourceLoader.exists("res://assets/tiles/floor_%s.png" % theme):
			themes_ok.append("no tile for '%s'" % theme)
		if not ResourceLoader.exists("res://assets/sfx/foot_%s.wav" % theme) and theme != "stone":
			themes_ok.append("no footstep clip for '%s'" % theme)
	_check(themes_ok.is_empty(), "every generated floor theme has art and a clip (%s)"
		% ", ".join(themes_ok))


## The set of floor themes the generator actually produces, asked of the generator rather than
## listed here — a hard-coded list would pass while the generator handed out something else.
func _generated_themes() -> Array:
	var seen := {}
	for seed_value in range(1, 41):
		var h := House.new()
		h.generate(8, seed_value)
		for cell in h.rooms:
			seen[h.rooms[cell].theme] = true
	return seen.keys()


func _constants() -> void:
	## The numbers that carry the whole look, read from the game rather than repeated here: a
	## test that hard-codes them only proves the test author can copy.
	print("constants...")
	var ppm := float(Run.PPM)
	var pitch := absf(float(Run.CAM_PITCH_DEG))
	var knight_px := float(Run.KNIGHT_M) * ppm * cos(deg_to_rad(pitch))
	_check(knight_px >= 95.0 and knight_px <= 135.0,
		"the knight's screen height is in the design band (%.1f px)" % knight_px)

	# The camera sign. A positive pitch puts the camera UNDER the floor looking up, which renders
	# as an empty frame and reads exactly like "the props stopped rendering" — it cost an hour
	# once. Cheaper to assert than to rediscover.
	_check(float(Run.CAM_PITCH_DEG) < 0.0,
		"the camera pitch is negative, so the camera is above the room (%0.1f)" % float(Run.CAM_PITCH_DEG))

	# Relics the run looks for, and the names it shows, must agree: a mismatch means the altar
	# refuses forever and the run cannot be finished.
	for id in Run.RELICS:
		_check(Run.RELIC_NAMES.has(id), "every relic has a display name ('%s')" % id)
	_check(Run.RELICS.size() == 2, "the run wants exactly two relics (%d)" % Run.RELICS.size())

	# Every loot string the generator can place must be one the run knows how to name.
	var generated := []
	var h := House.new()
	h.generate(8, 7)
	for cell in h.rooms:
		for c in h.rooms[cell].chests:
			generated.append(str(c["loot"]))
	var unnamed: Array = []
	for l in generated:
		if not Run.LOOT_NAMES.has(l):
			unnamed.append(l)
	_check(unnamed.is_empty(),
		"every generated loot type has a display name (unnamed: %s)" % ", ".join(unnamed))
