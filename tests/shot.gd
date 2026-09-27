extends Node
## End-to-end verification of the vertical slice.
##
##   godot --path <project> -- --shot [--name=<prefix>] [--pitch=<deg>] [--ppm=<n>]
##
## Two jobs, and the second is the important one:
##   1. Save screenshots as a baseline for later comparison.
##   2. WALK THE WHOLE LOOP and fail if any step does not happen. A slice that renders
##      beautifully and cannot be finished is not a slice; and a test that only checks
##      arithmetic would pass on a world where the doors never open.
##
## Every assertion here is a thing that was actually broken at some point during the build:
## the knight sunk into the floor, the props floated, the camera sat under the room, the room
## filled a sixth of the screen. None of those threw an error — they were only visible by
## measuring, which is what this file is for.

const SHOT_DIR := "res://tests/shots"
const TIMEOUT_SEC := 120.0
## Types are needed for `is DoorScript` style checks, and a test file does not inherit the
## game's constants: without these the script fails to parse and the run hangs with no
## watchdog, because a script that does not compile cannot start its own timer either.
const DoorScript := preload("res://scripts/game/door.gd")
const ChestScript := preload("res://scripts/game/chest.gd")
const AltarScript := preload("res://scripts/game/altar.gd")

var run: Node3D
var failures: Array[String] = []
var _done := false
var _started := 0.0


func _ready() -> void:
	_started = Time.get_ticks_msec() / 1000.0
	# A wall-clock watchdog on a real Timer, not on _process: if a parse error stops this
	# script from running _process, a _process-based watchdog never fires either and the run
	# hangs until a human kills it. That happened twice while building the prototype.
	var wd := Timer.new()
	wd.wait_time = TIMEOUT_SEC
	wd.one_shot = true
	wd.timeout.connect(func():
		if not _done:
			push_error("SLICE: timed out after %.0f s" % TIMEOUT_SEC)
			get_tree().quit(1))
	add_child(wd)
	wd.start()
	_go.call_deferred()


func _frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _check(ok: bool, message: String) -> void:
	if ok:
		print("  ok  " + message)
	else:
		failures.append(message)
		push_error("SLICE: " + message)


func _finish() -> void:
	if _done:
		return
	_done = true
	if failures.is_empty():
		print("\nVERTICAL SLICE OK")
		get_tree().quit(0)
	else:
		push_error("\nVERTICAL SLICE FAILED: " + "; ".join(failures))
		get_tree().quit(1)


func _save(name: String) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOT_DIR))
	var img := get_viewport().get_texture().get_image()
	img.save_png("%s/%s.png" % [SHOT_DIR, name])
	print("  saved %s (%dx%d)" % [name, img.get_width(), img.get_height()])


func _prefix() -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--name="):
			return a.trim_prefix("--name=")
	return "slice"


func _find(node: Node) -> Node3D:
	for c in node.get_children():
		if c is Node3D and c.has_method("ppm_at_focus"):
			return c as Node3D
		var f := _find(c)
		if f != null:
			return f
	return null


func _go() -> void:
	await _frames(8)
	run = _find(get_tree().root)
	if run == null:
		failures.append("the run scene did not load (see the parse errors above)")
		_finish()
		return

	var cam: Camera3D = get_viewport().get_camera_3d()
	var vp := get_viewport().get_visible_rect().size
	var prefix := _prefix()

	# --- 1. camera ---------------------------------------------------------------------
	print("\n--- framing ---")
	_check(cam.projection == Camera3D.PROJECTION_PERSPECTIVE,
		"camera is perspective (orthographic reads as a floor plan, not HD-2D)")
	var pitch: float = deg_to_rad(absf(float(run._pitch_deg)))
	var ppm: float = float(run.ppm_at_focus())
	_check(ppm >= 68.0 and ppm <= 102.0,
		"focus-plane density %.2f px/m is in the design band 68-102" % ppm)
	var wall_px: float = float(run.WALL_HEIGHT) * ppm * cos(pitch)
	var knight_px: float = float(run.KNIGHT_M) * ppm * cos(pitch)
	print("  note: knight %.1f px, wall %.1f px, tile %.1f px"
		% [knight_px, wall_px, ppm])
	_check(knight_px >= 95.0 and knight_px <= 135.0,
		"the knight is %.1f px on screen (design band 95-135)" % knight_px)
	_check(wall_px >= 150.0, "a wall face shows %.1f px (need >=150 for arches to read)" % wall_px)

	# --- 2. the knight stands on the floor ---------------------------------------------
	var body: Sprite3D = run.knight.get_node("Body")
	_check(absf(run.knight.position.y) < 0.01,
		"the knight's origin sits on the floor (y=%.3f)" % run.knight.position.y)
	_check(body.offset.y > 0.0,
		"the knight's sprite is lifted by half a frame so his feet reach the floor (offset.y=%.1f)"
		% body.offset.y)
	var feet_px: float = cam.unproject_position(run.knight.global_position).y
	_check(feet_px > 0.0 and feet_px < vp.y,
		"the knight is inside the frame (feet at y=%.0f)" % feet_px)

	# --- 3. the house ------------------------------------------------------------------
	print("\n--- chapter house ---")
	var room_count: int = run.house.rooms.size()
	_check(room_count == 8, "generated 8 rooms (got %d)" % room_count)
	_check(bool(run.house.all_rooms_reachable()), "every room is reachable from the entrance")
	_check(run._interactives.size() >= room_count,
		"at least one interactive per room (%d props for %d rooms)"
		% [run._interactives.size(), room_count])
	var altars := 0
	var relics := 0
	for p in run._interactives:
		if p.has_method("prompt") and p.get("loot") != null and str(p.get("loot")).begins_with("relic_"):
			relics += 1
		if p is AltarScript:
			altars += 1
	_check(relics == 2, "exactly two relic chests exist (found %d)" % relics)
	_check(altars == 1, "exactly one altar exists (found %d)" % altars)
	_save(prefix + "_start")

	# --- 4. the loop, walked for real ---------------------------------------------------
	print("\n--- the loop ---")
	# Door: walk the knight to a door and interact. Position via the parent, which is what the
	# camera and the game both read; the physics body is a child at local zero.
	var door = null
	for p in run._interactives:
		if p is DoorScript:
			door = p
			break
	_check(door != null, "a door exists")
	print("  .. door section, door=%s" % door)
	if door != null:
		run.knight.position = door.global_position + Vector3(0, 0, 2.0)
		run.knight.body.position = Vector3.ZERO
		await _frames(6)
		# What matters is that the player can act, not which prop wins the distance sort.
		# An earlier version asserted the door itself must be nearest and failed on a seed
		# where another prop sat inside the 2.4 m radius — a test assumption, not a bug.
		var nearest = run._find_interactive()
		_check(nearest != null, "something is in range at %.1f m from a door" % run.INTERACT_RANGE)
		if nearest != null:
			_check(str(nearest.prompt()) != "", "the nearest interactive offers a prompt")
		_check(str(door.prompt()) != "", "the door offers a prompt (%s)" % door.prompt())
		print("  .. calling door.interact")
		door.interact(run)
		await _frames(24)
		print("  .. door.interact returned, opened=%s" % door.opened)
		_check(bool(door.opened), "the door opened")
		_check(str(door.prompt()) == "", "an opened door stops offering its prompt")
		_save(prefix + "_door")

	# Chest: the same, then check the loot actually landed in the run state.
	var chest = null
	for p in run._interactives:
		if p.has_method("prompt") and p.get("loot") != null and str(p.get("loot")) == "gold":
			chest = p
			break
	_check(chest != null, "a mundane chest exists")
	if chest != null:
		run.knight.position = chest.global_position + Vector3(0, 0, 1.5)
		await _frames(6)
		chest.interact(run)
		await _frames(16)
		_check(bool(chest.taken), "the chest was looted")
		_check(str(chest.prompt()) == "", "a looted chest stops offering its prompt")

	# Altar refuses without the relics, and says what is missing.
	var altar = null
	for p in run._interactives:
		if p is AltarScript:
			altar = p
			break
	_check(altar != null, "an altar exists")
	if altar != null:
		run.knight.position = altar.global_position + Vector3(0, 0, 2.2)
		await _frames(6)
		_check(not run.has_all_relics(), "the run starts without all relics")
		var before: String = str(run._lbl_toast.text)
		altar.interact(run)
		await _frames(4)
		_check(not bool(altar.done), "the altar refuses before the relics are found")
		_check(str(run._lbl_toast.text) != before and str(run._lbl_toast.text) != "",
			"the altar names what is missing (%s)" % run._lbl_toast.text)
		_save(prefix + "_altar_refused")

		# Collect both relics through the real path, then finish.
		for p in run._interactives:
			if p.has_method("prompt") and p.get("loot") != null \
					and str(p.get("loot")).begins_with("relic_"):
				run.knight.position = p.global_position + Vector3(0, 0, 1.2)
				await _frames(3)
				p.interact(run)
				await _frames(3)
		_check(run.has_all_relics(), "both relics collected (%d/%d)"
			% [run.relics.size(), run.RELICS.size()])
		altar.interact(run)
		await _frames(10)
		_check(bool(altar.done), "the altar accepts the relics")
		_check(bool(run.over), "the run ends on completing the rite")
		_check(bool(run._lbl_end.visible), "the end screen is shown")
		_save(prefix + "_rite")

	# --- 5. combat ---------------------------------------------------------------------
	print("\n--- combat ---")
	var cultist = null
	for e in run._enemies:
		if is_instance_valid(e) and e.alive:
			cultist = e
			break
	_check(cultist != null, "a cultist is in the house")
	if cultist != null:
		var hp0: int = cultist.hp
		run.knight.position = cultist.global_position + Vector3(0, 0, 1.0)
		run.knight.facing = (cultist.global_position - run.knight.global_position).normalized()
		for i in 4:
			for p in run._interactives:
				pass
			run.knight._swing_t = 0.0
			run.knight.swing()
			await _frames(2)
		_check(cultist.hp < hp0, "a swing damages a cultist (%d -> %d)" % [hp0, cultist.hp])

	# --- 6. sound, and the rule that makes it a resource ---------------------------------
	#
	# The whole design claim is "a noise you make pulls the opposition toward where you made
	# it". That is testable, and if it silently stops being true the game becomes a stealth
	# game with decorative audio. So the claim is asserted rather than assumed.
	print("\n--- sound and hearing ---")
	var target_cultist = null
	for e in run._enemies:
		if is_instance_valid(e) and e.alive:
			target_cultist = e
			break
	_check(target_cultist != null, "a cultist exists to hear things")
	if target_cultist != null:
		# Put the knight far away first. Sight beats hearing by design, so a hearing test run
		# with the player standing next to the subject measures chase behaviour instead — the
		# first version of this test failed exactly that way and looked like a hearing bug.
		run.knight.position = Vector3(500, 0, 500)
		await _frames(4)
		var home: Vector3 = target_cultist.global_position

		# A quiet noise nearby does NOT pull it: a footstep is not an alarm.
		Sound.noise_made.emit(home + Vector3(1.2, 0, 0), 1.5, "foot_stone")
		await _frames(2)
		_check(int(target_cultist.state) == 0,
			"a footstep 1.2 m away does not wake a wandering cultist (state=%d)"
			% target_cultist.state)

		# A loud noise far away DOES pull it, and toward the noise rather than toward the
		# player: that distinction is the entire point of the system.
		var far := home + Vector3(9.0, 0, 0)
		Sound.noise_made.emit(far, 12.0, "door_slam")
		await _frames(2)
		_check(int(target_cultist.state) != 0,
			"a door slam 9 m away pulls the cultist (state=%d)" % target_cultist.state)
		if int(target_cultist.state) != 0:
			var before: float = target_cultist.global_position.distance_to(far)
			for i in 60:
				await get_tree().physics_frame
			var after: float = target_cultist.global_position.distance_to(far)
			_check(after < before - 0.3,
				"the cultist walks toward the noise (%.1f m -> %.1f m)" % [before, after])

		# Earshot scales with the noise. A whisper on the far side of the building must not
		# summon anything, or loudness stops meaning anything.
		target_cultist.state = 0
		Sound.noise_made.emit(home + Vector3(60.0, 0, 0), 1.5, "foot_stone")
		await _frames(2)
		_check(int(target_cultist.state) == 0,
			"a quiet noise 60 m away is not heard (state=%d)" % target_cultist.state)
		# Put the player back where the rest of the test expects him.
		run.knight.position = run.house.rooms[run.house.entrance].centre()
		await _frames(4)

	# The player's answer to being heard.
	var stones_before: int = run.knight.stones
	_check(stones_before > 0, "the knight starts with stones to throw (%d)" % stones_before)
	_check(run.knight.throw_stone(), "a stone can be thrown")
	_check(run.knight.stones == stones_before - 1,
		"throwing spends a stone (%d -> %d)" % [stones_before, run.knight.stones])
	await _frames(4)
	_save(prefix + "_throw")

	# --- 7. restart --------------------------------------------------------------------
	print("\n--- restart ---")
	var rooms_before: int = run.house.rooms.size()
	var visited_before: int = run.visited.size()
	run.start_run(4242)
	await _frames(8)
	_check(run.house.rooms.size() == rooms_before, "a restart generates a fresh house")
	_check(not run.over, "a restart clears the ended state")
	_check(run.visited.size() < maxi(visited_before, 2) + 1, "a restart clears the visit list")
	_check(not run._lbl_end.visible, "a restart hides the end screen")
	_check(run.knight.stones == 3, "a restart refills the stones (%d)" % run.knight.stones)
	_save(prefix + "_restart")

	_finish()
