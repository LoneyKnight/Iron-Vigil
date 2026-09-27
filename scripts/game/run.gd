extends Node3D
## Iron Vigil — the run. Generates a chapter house, puts the knight in it, and runs the loop:
## explore, open doors, search chests, find two relics, carry them to the altar, end the run.
##
## One scene, one job. Everything an actor needs is injected (the camera, the depth scale,
## the interaction check); everything that outlives an actor — relics, run state, the end
## screen — lives here, because those are the things a second player would need replicated.
##
## Camera numbers are solved, not chosen; see tools/design/style_spec.md §1 and the sweep in
## tests/diag.gd. Do not change them without re-running that sweep, and never fix the art to
## match a broken camera.

const House := preload("res://scripts/game/chapter_house.gd")
const RoomBuilder := preload("res://scripts/game/room_builder.gd")
const Knight := preload("res://scripts/game/knight.gd")
const Cultist := preload("res://scripts/game/cultist.gd")
const DoorScript := preload("res://scripts/game/door.gd")
const ChestScript := preload("res://scripts/game/chest.gd")
const AltarScript := preload("res://scripts/game/altar.gd")
const Util := preload("res://scripts/game/prop_util.gd")

# --- camera: solved from the style spec, verified by tests/shot.gd ---------------------
const PPM := 85.0                     # screen px per metre of ground at the focus plane
const VIEWPORT := Vector2(1920, 1080)
## Solved by sweeping pitch against the measured room coverage now that real art is in the
## scene (tools/art/sweep.py, tools/design/concepts/camera_sweep.png). At 85 px/m and a 7 m room:
##   pitch 28 -> knight 135 px, wall 345 px, but a 7 m room does not fill the frame and the view
##               reads as a corridor looking through walls
##   pitch 34 -> knight 127 px, wall 324 px, room and both flanking doorways in frame  <- this
##   pitch 40 -> knight 117 px, wall 299 px, flatter, the depth starts to go
##   pitch 46 -> knight 107 px, wall 272 px, back to a floor plan
const CAM_PITCH_DEG := -36.0          # signed: negative is above the room
const CAM_FOV := 24.0
const CAM_DIST := VIEWPORT.y / (2.0 * PPM * tan(deg_to_rad(CAM_FOV * 0.5)))
const CAM_FOLLOW := 9.0

const RELICS := ["relic_dagger", "relic_tallow"]
const RELIC_NAMES := {"relic_dagger": "仪式匕首", "relic_tallow": "守夜油脂"}
const LOOT_NAMES := {
	"gold": "金币", "bandage": "绷带",
	"relic_dagger": "仪式匕首", "relic_tallow": "守夜油脂",
}
const INTERACT_RANGE := 2.4
## How far a noise carries, in metres, per unit of threat. The ratio matters more than the
## absolute: a footstep (1.5) reaches 2.6 m and a shouldered door (14) reaches 24 m. Tuned by
## ear, and tunable in one place because it is one number.
const HEAR_PER_THREAT := 1.7
const STONE_GRAVITY := 14.0

# --- values the camera tests read. Kept here so tests/shot.gd can verify the framing of the
# --- REAL game rather than a prototype that happens to be nearby.
const KNIGHT_M := 1.80
const WALL_HEIGHT := RoomBuilder.WALL_HEIGHT
const HH := House.ROOM_M * 0.5
const ROOM_TILES := 7

var _noise_level := 0.0       # the loudest recent noise the player made, for the HUD meter
var _noise_t := 0.0           # seconds left before the meter starts falling
var _environment: Environment
var _ambient_lit := false
var _pitch_deg := CAM_PITCH_DEG
var _dist := CAM_DIST
var house: House
var knight: Knight
var camera: Camera3D
var level: RoomBuilder

var relics := {}                      # relic id -> true
var killed := 0
var visited := {}                     # Vector2i -> true
var started_ms := 0
var over := false
var over_text := ""

var _rooms: Dictionary = {}            # Vector2i -> Node3D
var _enemies: Array = []
var _interactives: Array = []
var _nearby = null                    # the interactive currently in range
var _lx := 0.0
var _mouse_world := Vector3.ZERO

# --- HUD, built in code: it is six labels, and a .tscn would be more to keep in sync ----
var _hud: CanvasLayer
var _lbl_status: Label
var _lbl_prompt: Label
var _lbl_toast: Label
var _lbl_end: Label
var _toast_t := 0.0
var _lbl_noise: Label


func _ready() -> void:
	_read_camera_args()
	_build_environment()
	_build_camera()
	_build_hud()
	start_run()
	_report_budget()


## --pitch=<deg> --ppm=<px per metre> --name=<shot prefix>. The framing was solved by sweeping
## these against the measured room coverage (tests/diag.gd, tools/art/sweep.py); keeping the
## sweep runnable is what lets the numbers be re-checked after the art changes underneath them
## instead of being taken on trust.
##
## PITCH IS SIGNED and the sign is not cosmetic: a negative pitch puts the camera above the room
## looking down, a positive one puts it below the floor looking up. Passing `--pitch=36` once
## produced a frame containing nothing but the underside of the floor, which reads exactly like
## "the props stopped rendering". Magnitude is what callers think in, so the sign is normalised.
func _read_camera_args() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--pitch="):
			_pitch_deg = -absf(float(a.trim_prefix("--pitch=")))
		elif a.begins_with("--ppm="):
			var ppm := float(a.trim_prefix("--ppm="))
			if ppm > 1.0:
				_dist = VIEWPORT.y / (2.0 * ppm * tan(deg_to_rad(CAM_FOV * 0.5)))


# =======================================================================================
# run lifecycle
# =======================================================================================

func start_run(seed_value: int = 0) -> void:
	over = false
	over_text = ""
	relics.clear()
	killed = 0
	visited.clear()
	_enemies.clear()
	_interactives.clear()
	_nearby = null
	started_ms = Time.get_ticks_msec()
	_lbl_end.visible = false

	if level:
		level.queue_free()
	if knight:
		knight.queue_free()

	house = House.new()
	house.generate(8, seed_value)
	level = RoomBuilder.new()
	level.name = "Level"
	add_child(level)
	level.build(house)

	for cell in house.rooms:
		_place_room_contents(house.rooms[cell])

	var start_room: House.Room = house.rooms[house.entrance]
	knight = Knight.new()
	knight.name = "Knight"
	add_child(knight)
	knight.position = start_room.centre() + Vector3(0, 0.0, -2.2)
	knight.apply_depth_scale(cos(deg_to_rad(absf(_pitch_deg))))
	knight.died.connect(_on_knight_died)
	knight.swung.connect(_on_knight_swung)
	knight.threw.connect(_on_stone_thrown)
	for e in _enemies:
		e.set_target(knight)

	# Sound: the listener is the knight, and every noise the world makes is offered to
	# everything that can hear it. Connecting here rather than inside Sound keeps the rule
	# visible — the run decides who has ears.
	Sound.set_listener(knight)
	if not Sound.noise_made.is_connected(_on_noise):
		Sound.noise_made.connect(_on_noise)

	camera.position = _camera_target()
	visited[house.entrance] = true
	_toast("在 %d 个房间里找到两件圣物，带到祭坛" % house.rooms.size(), 5.0)


func _place_room_contents(room: House.Room) -> void:
	for spec in room.chests:
		var c := ChestScript.new()
		c.name = "Chest"
		add_child(c)
		c.build(spec["at"], str(spec["loot"]))
		_interactives.append(c)
	for at in room.enemy_spawn:
		var e := Cultist.new()
		e.name = "Cultist"
		add_child(e)
		e.setup(at)
		e.struck.connect(_on_knight_hurt)
		_enemies.append(e)
	for dir in room.linked:
		# One door per link, built from the lower cell id on both sides so a shared doorway
		# produces exactly one door instead of two stacked on top of each other.
		var nb: Vector2i = room.linked[dir]
		if nb < room.cell:
			continue
		var d := DoorScript.new()
		d.name = "Door"
		add_child(d)
		d.build(room.cell, dir, room.door_position(dir))
		_interactives.append(d)
	if room.has_altar:
		var a := AltarScript.new()
		a.name = "Altar"
		add_child(a)
		a.build(room.centre() + Vector3(0.0, 0.0, -2.0))
		_interactives.append(a)


func finish_rite(_altar) -> void:
	var secs := (Time.get_ticks_msec() - started_ms) / 1000.0
	over = true
	over_text = "仪式完成\n"
	over_text += "%d 个房间 · 击杀 %d · 用时 %d:%02d\n" % [
		visited.size(), killed, int(secs) / 60, int(secs) % 60]
	over_text += "按 R 再来一局"
	_lbl_end.text = over_text
	_lbl_end.visible = true


func _on_knight_died() -> void:
	over = true
	over_text = "你倒下了\n%d 个房间 · 击杀 %d\n按 R 再来一局" % [visited.size(), killed]
	_lbl_end.text = over_text
	_lbl_end.visible = true


# =======================================================================================
# loop
# =======================================================================================

func collect(loot: String, at: Vector3) -> void:
	if loot in RELICS:
		relics[loot] = true
		# Two different sounds for two different sizes of event. Ordinary loot is a bright
		# little chime; a relic is long and low and outlasts the player's movement, so the
		# player can tell they picked up the thing that matters without reading a line.
		Sound.play("relic_pickup", at, 8.0, 1.0, 0.0, knight)
		_toast("获得圣物：%s（%d/%d）" % [RELIC_NAMES.get(loot, loot), relics.size(), RELICS.size()], 4.0)
	else:
		Sound.play("pickup", at, 2.0, 1.0, 0.0, knight)
		_toast("获得 %s" % LOOT_NAMES.get(loot, loot), 2.0)


func has_all_relics() -> bool:
	return relics.size() >= RELICS.size()


func missing_relics_text() -> String:
	var missing: Array = []
	for r in RELICS:
		if not relics.has(r):
			missing.append(RELIC_NAMES.get(r, r))
	return "、".join(missing)


func say(text: String) -> void:
	_toast(text, 3.0)


func _toast(text: String, seconds: float) -> void:
	_lbl_toast.text = text
	_lbl_toast.modulate.a = 1.0
	_toast_t = seconds


func _on_knight_swung(at: Vector3, facing: Vector3) -> void:
	# Melee is a distance and a half-angle check on the host side of the swing, not a physics
	# query: with a handful of enemies, an exact hitbox buys nothing and a cone is trivial to
	# reason about when it feels wrong.
	for e in _enemies:
		if not is_instance_valid(e) or not e.alive:
			continue
		if knight.already_hit(e.get_instance_id()):
			continue
		var to: Vector3 = e.global_position - at
		to.y = 0.0
		if to.length() > Knight.SWING_REACH + 0.4:
			continue
		if to.length() > 0.05 and facing.dot(to.normalized()) < 0.35:
			continue
		knight.mark_hit(e.get_instance_id())
		e.take_damage(34)
		if not e.alive:
			killed += 1
			_toast("击杀邪教徒（%d）" % killed, 1.6)


func _on_knight_hurt(hp: int) -> void:
	if hp > 0:
		_toast("受伤 · %d" % hp, 1.2)


# =======================================================================================
# hearing: the other half of the sound system
# =======================================================================================

## Everything that can hear a noise is told about it. This is the rule that makes sound a
## resource rather than an effect: a noise the player makes pulls the opposition toward the
## place it was made, so making one is a decision with a cost.
##
## There is no line-of-sight test here on purpose. Sound goes around corners and through
## walls; that is precisely why it is useful and precisely why it is dangerous.
##
## `source` is what keeps the opposition from alerting itself. A cultist's idle chant goes
## through the same mixer — the player must hear it from the next room — but an enemy noise
## must not wake another enemy, or one chant cascades through the whole building and the
## player's own noise stops being the thing that matters. Only the player has ears here.
func _on_noise(at: Vector3, threat: float, kind: String, source: Node = null) -> void:
	if source != null and source != knight:
		return
	# The player's own noise shows on the HUD. Without a visible level, "running is loud" is an
	# instruction the player has to be told; with one, it is a dial they watch while deciding.
	# The meter decays, because the state that matters is "how loud am I right now".
	if source == knight:
		_noise_level = maxf(_noise_level, threat)
		_noise_t = 1.6
	var earshot := threat * HEAR_PER_THREAT
	for e in _enemies:
		if not is_instance_valid(e) or not e.alive:
			continue
		if e.global_position.distance_to(at) <= earshot:
			e.hear_noise(at, threat)


## The player's answer to being heard: a stone that lands somewhere else.
##
## Simulated here rather than as a physics body because the whole point is WHERE it lands and
## how loud that is; a rigid body would add a solver, a collider layer and a spawn/despawn
## problem to answer a question that is one parabola.
func _on_stone_thrown(from: Vector3, toward: Vector3) -> void:
	var mesh := MeshInstance3D.new()
	var ball := SphereMesh.new()
	ball.radius = 0.09
	ball.height = 0.18
	mesh.mesh = ball
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("5a5751")
	mat.roughness = 1.0
	mesh.material_override = mat
	add_child(mesh)

	# Throw along the aim, with an upward arc so it clears furniture and reads as a throw.
	var dir := Vector3(toward.x, 0.0, toward.z).normalized()
	var flight := Vector3(dir.x, 0.0, dir.z) * Knight.THROW_SPEED + Vector3(0, 6.4, 0)
	var t := 0.0
	var at := from
	while t < 3.0:
		var dt := get_process_delta_time()
		if dt <= 0.0:
			dt = 1.0 / 60.0
		t += dt
		flight.y -= STONE_GRAVITY * dt
		at += flight * dt
		if at.y <= 0.12:
			break
		mesh.global_position = at
		await get_tree().process_frame
		if not is_instance_valid(mesh):
			return

	var landed := Vector3(at.x, 0.09, at.z)
	mesh.global_position = landed
	# The landing is what matters: it is the loudest thing the player can arrange to happen
	# somewhere they are not.
	Sound.play("stone_impact", landed, Knight.NOISE_STONE_LAND, 1.0, 0.0, knight)
	_toast("石头落地 · 动静传得很远", 1.6)
	var tw := create_tween()
	tw.tween_property(mesh, "scale", Vector3(0.01, 0.01, 0.01), 0.6)
	tw.tween_callback(mesh.queue_free)


## The floor under the player decides which footstep clip plays, so the mix changes as they
## move through the building. One string on the knight; the room owns the material.
func _update_surface() -> void:
	var cell := Vector2i(
		roundi(knight.global_position.x / House.ROOM_PITCH),
		roundi(knight.global_position.z / House.ROOM_PITCH))
	var room = house.rooms.get(cell)
	knight.surface = "stone" if room == null else str(room.theme)


# =======================================================================================
# per frame
# =======================================================================================

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_R:
			start_run()
			return
		if event.keycode == KEY_E and not over:
			# Ask for the target now instead of trusting the cached one. The cache is
			# refreshed once a frame, so a player who walks up to a door and presses E in the
			# same frame would otherwise be acting on last frame's answer — and the same
			# staleness makes the interaction untestable.
			var target = _find_interactive()
			if target != null:
				target.interact(self)
			return
		if event.keycode == KEY_G and not over:
			knight.throw_stone()
			return
		if event.keycode == KEY_F4:
			## The darkness A/B. Neither state is wrong: 0.62 is the shipped mood, 1.4 is the
			## inspection state. Keeping both on one key stops the mood from silently becoming
			## the thing that hides bugs — which is how a whole previous project shipped a game
			## nobody could see.
			_ambient_lit = not _ambient_lit
			if _environment:
				_environment.ambient_light_energy = 2.0 if _ambient_lit else 0.95
			print("ambient -> %s" % ("inspection 2.0" if _ambient_lit else "shipped 0.95"))
			return
	if event is InputEventMouseButton and event.pressed \
			and event.button_index == MOUSE_BUTTON_LEFT and not over:
		if knight.swing():
			Sound.play("swing", knight.global_position, Knight.NOISE_SWING, 1.0, 0.0, knight)


func _physics_process(_delta: float) -> void:
	if over or knight == null:
		return
	_update_surface()
	var room_cell := Vector2i(
		roundi(knight.global_position.x / House.ROOM_PITCH),
		roundi(knight.global_position.z / House.ROOM_PITCH))
	if house.rooms.has(room_cell) and not visited.has(room_cell):
		visited[room_cell] = true
		_toast("进入第 %d 个房间" % visited.size(), 1.4)


func _process(delta: float) -> void:
	if knight == null:
		return
	camera.position = camera.position.lerp(_camera_target(),
		clampf(delta * CAM_FOLLOW, 0.0, 1.0))
	if not over:
		knight.face_mouse(camera, get_viewport().get_mouse_position())
		_nearby = _find_interactive()
	_update_hud(delta)


func _camera_target() -> Vector3:
	var rad := deg_to_rad(_pitch_deg)
	return knight.position + Vector3(0, -sin(rad) * _dist, cos(rad) * _dist)


## Nearest interactive within range. Distance, not an Area3D: with a dozen props, sorting by
## distance is exact and gives the player the thing they are actually closest to, which is
## what "the prompt shows the thing I mean" requires.
func _find_interactive():
	var best = null
	var best_d := INTERACT_RANGE
	for p in _interactives:
		if not is_instance_valid(p):
			continue
		var text: String = p.prompt()
		if text == "":
			continue
		var d: float = p.global_position.distance_to(knight.global_position)
		if d < best_d:
			best_d = d
			best = p
	return best


func _update_hud(delta: float) -> void:
	var relic_txt := ""
	for r in RELICS:
		relic_txt += ("◆ " if relics.has(r) else "◇ ") + str(RELIC_NAMES.get(r, r)) + "   "
	_lbl_status.text = "生命 %d/%d      圣物 %d/%d      石头 %d\n%s\n房间 %d/%d   击杀 %d" % [
		knight.hp, Knight.MAX_HP, relics.size(), RELICS.size(), knight.stones, relic_txt,
		visited.size(), house.rooms.size() if house else 0, killed]
	if _nearby != null and is_instance_valid(_nearby):
		_lbl_prompt.text = "[E] " + str(_nearby.prompt())
		_lbl_prompt.visible = true
	else:
		_lbl_prompt.visible = false
	if _toast_t > 0.0:
		_toast_t -= delta
		if _toast_t < 0.6:
			_lbl_toast.modulate.a = clampf(_toast_t / 0.6, 0.0, 1.0)
	else:
		_lbl_toast.modulate.a = 0.0

	# Noise meter. The player's own noise is the resource they spend, so it has to be visible:
	# a bar of blocks plus the earshot it buys. The decay is deliberate — the thing that matters
	# is "how loud am I right now", not "how loud have I been".
	if _noise_t > 0.0:
		_noise_t -= delta
	else:
		_noise_level = maxf(0.0, _noise_level - delta * 6.0)
	var blocks := 0
	if _noise_level > 0.1:
		blocks = clampi(int(ceil(_noise_level / 2.0)), 1, 7)
	var word := "安静"
	if _noise_level >= 10.0:
		word = "极响"
	elif _noise_level >= 6.0:
		word = "很响"
	elif _noise_level >= 3.0:
		word = "有动静"
	elif _noise_level >= 1.0:
		word = "脚步"
	_lbl_noise.text = "声响  %s%s   %s   传 %.0f m" % [
		"■".repeat(blocks), "·".repeat(7 - blocks), word, _noise_level * HEAR_PER_THREAT]


# =======================================================================================
# setup helpers
# =======================================================================================

func _build_environment() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color("05050a")
	# Fog is the depth cue that a 7 m room cannot provide on its own: it separates the near
	# flagstones from the far wall and makes the doorway read as an opening rather than a hole.
	e.fog_enabled = true
	e.fog_light_color = Color("141422")
	e.fog_density = 0.006
	e.fog_sky_affect = 0.0
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	# The ambient is COOL and the lantern is WARM. That split is the whole colour story: the
	# stone reads blue-grey where nothing is lighting it, and the pool around the player is
	# tallow-yellow. A neutral ambient makes both the same grey and the lantern stops being a
	# light source and becomes a brightness control.
	e.ambient_light_color = Color("55618c")
	# Shipped value, reached by looking at frames rather than by reasoning about numbers. The
	# shipped mood is dark, but not so dark that the architecture vanishes — the lantern then has
	# something to reveal, which is the whole lighting design. F4 toggles an inspection value so
	# the next person can do the same instead of guessing, and so that a mood can never quietly
	# become the thing that hides a bug.
	e.ambient_light_energy = 0.95
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	e.tonemap_exposure = 1.25
	e.tonemap_white = 5.0
	e.ssao_enabled = true
	e.ssao_radius = 1.6
	e.ssao_intensity = 2.4
	e.glow_enabled = true
	e.glow_intensity = 0.45
	e.glow_bloom = 0.06
	e.glow_hdr_threshold = 1.15
	env.environment = e
	add_child(env)
	_environment = e


func _build_camera() -> void:
	camera = Camera3D.new()
	camera.name = "Camera"
	camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	camera.fov = CAM_FOV
	camera.near = 0.05
	camera.far = 220.0
	camera.rotation_degrees = Vector3(_pitch_deg, 0, 0)
	add_child(camera)
	camera.make_current()


func _build_hud() -> void:
	_hud = CanvasLayer.new()
	_hud.name = "Hud"
	add_child(_hud)
	_lbl_status = _label(Vector2(24, 18), 20, Color(0.94, 0.88, 0.72))
	_lbl_prompt = _label(Vector2(24, 610), 26, Color(1.0, 0.88, 0.55))
	_lbl_toast = _label(Vector2(24, 664), 20, Color(0.86, 0.86, 0.9))
	# The noise meter: the player's own noise is the resource they spend, so it is drawn.
	_lbl_noise = _label(Vector2(24, 158), 18, Color(0.78, 0.86, 1.0))
	_lbl_end = _label(Vector2(0, 380), 40, Color(1.0, 0.86, 0.5))
	_lbl_end.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_lbl_end.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	_lbl_end.offset_top = 380.0
	_lbl_end.offset_bottom = 700.0
	_lbl_end.visible = false


func _label(at: Vector2, size: int, colour: Color) -> Label:
	var l := Label.new()
	l.position = at
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", colour)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.95))
	l.add_theme_constant_override("outline_size", 6)
	_hud.add_child(l)
	return l


# =======================================================================================
# camera budget: printed on start and asserted by tests/shot.gd
# =======================================================================================

## Nominal pixels per metre at the focus plane. With a perspective camera this is exact only
## at the centre of the frame; the edges differ by a few percent, which is the price of the
## depth that makes the scene read as 3D at all (style_spec.md §1.1).
func ppm_at_focus() -> float:
	return VIEWPORT.y / (2.0 * _dist * tan(deg_to_rad(CAM_FOV * 0.5)))


## The framing, stated once. The derivation lives in style_spec.md §1.2 and the measured
## calibration lives in tests/shot.gd; this is the summary line that makes drift visible.
func _report_budget() -> void:
	var pitch := deg_to_rad(absf(_pitch_deg))
	var ppm := ppm_at_focus()
	print("--- Iron Vigil camera budget ---")
	print("viewport            : %d x %d" % [VIEWPORT.x, VIEWPORT.y])
	print("projection          : perspective, fov %.0f deg at %.1f m" % [CAM_FOV, _dist])
	print("pitch               : %.0f deg" % _pitch_deg)
	print("px per floor metre  : %.2f at focus" % ppm)
	print("one tile on screen  : %.1f px at focus" % ppm)
	print("height on screen    : %.1f px per metre of height (cos(pitch)=%.3f)"
		% [ppm * cos(pitch), cos(pitch)])
	print("knight on screen    : %.1f px  (%.2f m tall)" % [KNIGHT_M * ppm * cos(pitch), KNIGHT_M])
	print("wall face on screen : %.1f px for a %.1f m wall"
		% [WALL_HEIGHT * ppm * cos(pitch), WALL_HEIGHT])
