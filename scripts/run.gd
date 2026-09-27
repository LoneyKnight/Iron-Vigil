extends Node3D
## Iron Vigil — technique prototype.
##
## What this proves, in order of importance:
##   1. A knight sprite authored at one size lands on screen at the size the style spec
##      demands (59 px), driven by a real Camera3D rather than a CanvasItem zoom.
##   2. The room, the walls and the props read at 32 screen pixels per tile.
##   3. A lantern with real shadow-casting is the only light, and it occludes.
##
## What this is not: there is no networking, no rules, no content. It is one room and one
## walking knight, built to settle the camera before any gameplay is written.
##
## Camera maths (style_spec.md §1, solved by tools/art/camera.py). The world is metric:
## 1 tile = 1 m, and the camera is orthographic, so the mapping from metres to pixels is a
## single number ON THE GROUND PLANE.
##
## The subtlety that the first version of this file got wrong: at a pitched camera a metre
## of FLOOR and a metre of HEIGHT are foreshortened differently — cos(pitch) and sin(pitch)
## respectively. Quoting one density for both is what made the spec claim a 59 px knight
## while the engine rendered 36 px. So there are two numbers here, and both are checked:
##   PPM  - screen pixels per metre ON THE GROUND. Sets tile size and how much is visible.
##   and the figure's screen height follows from PPM * sin(pitch) * world height.
##
## PERSPECTIVE, not orthographic. The first playable frame was orthographic and it did not
## read as HD-2D at all: a parallel projection has no vanishing point, so the room came out
## as a flat floor plan with a light spot on it. The look being chased depends on a real 3D
## scene seen at an angle, where depth is conveyed by convergence, fog and a shallow focal
## plane. Density is the cost: with perspective the same tile is a few percent larger at the
## bottom of the frame than the top, so "42 px per tile" becomes a nominal value quoted at
## the camera's focus point. That is the honest trade, and it is the one HD-2D itself makes.
const PPM := 42.43                    # nominal screen px per metre of ground, at focus
const VIEWPORT := Vector2(1920, 1080)
const TILE := 1.0
const ROOM_TILES := 13
const HH := ROOM_TILES / 2.0

## Camera. FOV is the fixed choice; the DISTANCE is solved from the target density so the
## two can never disagree. (The first perspective attempt hard-coded both, and 21 deg at
## 26 m came out at 112 px per metre — a 165 px knight and 1.3 rooms on screen, i.e. an
## action-game close-up rather than an HD-2D room.)
##
## PITCH is what separates "top-down" from "HD-2D", and it is also the main lever on how
## large a figure appears — because a standing height is foreshortened by cos(pitch).
## Measured consequences at ppm = 42.43, 1.8 m figure, 3.2 m wall:
##     pitch 55 deg -> figure 44 px, wall face 78 px
##     pitch 45 deg -> figure 54 px, wall face 96 px
##     pitch 40 deg -> figure 58 px, wall face 104 px
## 45 is the pick: the figure clears the readability band and the walls are still tall.
const CAM_PITCH_DEG := -45.0
const CAM_FOV := 34.0                 # a normal, undistorted lens
## Distance that makes PPM pixels per metre land on the focus plane:
##     PPM = VH / (2 * d * tan(fov/2))   ->   d = VH / (2 * PPM * tan(fov/2))
const CAM_DIST := VIEWPORT.y / (2.0 * PPM * tan(deg_to_rad(CAM_FOV * 0.5)))
const CAM_FOLLOW := 9.0

const WALL_HEIGHT := 3.2
const KNIGHT_M := 1.80                # 1.8 m tall; his screen height follows from the camera
const KNIGHT_SPEED := 4.2             # m/s; reads as a stride, not a slide

const INK := Color("16130f")
const STONE := Color("6a665c")
const STONE_DARK := Color("4a4741")
const IRON := Color("3a3a3e")
const OXBLOOD := Color("5a1e1e")
const TALLOW := Color("ffc46e")

var camera: Camera3D
var knight: Node3D
var lantern: SpotLight3D
var _environment: Environment
var _ambient_lit := true
## Camera values are constants by default but overridable from the command line, because
## "which pitch looks right" is a judgement call that has to be seen, not argued:
##   godot --path . -- --shot --pitch=38 --ppm=52 --name=pitch38
var _pitch_deg := CAM_PITCH_DEG
var _dist := CAM_DIST
var _shot_name := "tile32_knight59"
var _yaw := 0.0
var _hud: Label
var _frames := 0


func _ready() -> void:
	_read_camera_args()
	_build_room()
	_build_knight()
	_build_camera()
	_build_light()
	_build_hud()
	_report_budget()


## --pitch=<deg> --ppm=<px per metre> --name=<shot name>. Kept here so the camera sweep is
## a command-line loop rather than five edited copies of this file.
func _read_camera_args() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--pitch="):
			_pitch_deg = float(a.trim_prefix("--pitch="))
		elif a.begins_with("--ppm="):
			var ppm := float(a.trim_prefix("--ppm="))
			if ppm > 1.0:
				_dist = VIEWPORT.y / (2.0 * ppm * tan(deg_to_rad(CAM_FOV * 0.5)))
		elif a.begins_with("--name="):
			_shot_name = a.trim_prefix("--name=")


# ---------------------------------------------------------------------------------------
# room
# ---------------------------------------------------------------------------------------

## Environment art is authored at the ATLAS size the game displays (style_spec.md §0): the
## floor texture is drawn so one tile of it is exactly TILE_PX on screen. It is generated
## procedurally rather than by the image model — a floor repeats 169 times per room and
## must be quiet, and the model insists on painting dioramas (style_spec.md §6).
const TILE_PX := 42                   # procedural canvas for one floor tile
const WALL_PX := 21                   # one wall course, half a tile tall


func _floor_texture() -> ImageTexture:
	## 3x3 tiles with the mortar line on the tile border, so a 3x3 arrangement reproduces
	## seamlessly and one texture covers three tiles of the room.
	var t := TILE_PX
	var size := t * 3
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	for y in size:
		for x in size:
			var tx := x % t
			var ty := y % t
			# Cheap deterministic wobble so slabs are not perfectly identical, and a
			# mortar seam on the tile border so the 3x3 pre-tiling lines up.
			var n := float((x * 7 + y * 13 + (x / 8) * 5) % 9) / 9.0
			if tx == 0 or ty == 0:
				img.set_pixel(x, y, STONE_DARK.darkened(0.10 + n * 0.06))
			else:
				var v := STONE.darkened(0.02 + n * 0.07)
				# One faint crack per slab, lower half only: a couple of readable features
				# beat covering the floor in noise at this density.
				if tx == t / 2 and ty > t / 2:
					v = v.darkened(0.16)
				img.set_pixel(x, y, v)
	return ImageTexture.create_from_image(img)


func _wall_texture() -> ImageTexture:
	## Ashlar courses in running bond. A vertical face at 45 deg still shows its face, so
	## it needs the floor's value discipline plus a stronger joint, otherwise the room
	## outline disappears into the floor value.
	var course := WALL_PX
	var w := course * 2
	var h := course * 2
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	for y in h:
		for x in w:
			var row := y / course
			var offset := (row % 2) * (w / 4)
			var in_joint: bool = (y % course == 0) or ((x + offset) % w == 0)
			var n := float((x * 11 + y * 5 + row * 3) % 7) / 7.0
			var base := STONE.darkened(0.18)
			img.set_pixel(x, y, IRON.lerp(base, 0.62) if in_joint else base.darkened(n * 0.08))
	return ImageTexture.create_from_image(img)


func _build_room() -> void:
	var span := float(ROOM_TILES) * TILE
	var floor_mat := StandardMaterial3D.new()
	floor_mat.albedo_texture = _floor_texture()
	floor_mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	# The texture already holds 3x3 tiles, so the UV repeat is ROOM/3 in each direction.
	floor_mat.uv1_scale = Vector3(float(ROOM_TILES) / 3.0, float(ROOM_TILES) / 3.0, 1.0)
	floor_mat.roughness = 0.95
	_slab(Vector3(span, 0.2, span), Vector3(0, -0.1, 0), floor_mat)

	var wall_mat := StandardMaterial3D.new()
	wall_mat.albedo_texture = _wall_texture()
	wall_mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	# The wall texture holds 2x2 tiles === 2 m x 2 m of face (WALL_PX is half a tile).
	wall_mat.uv1_scale = Vector3(span / 2.0, WALL_HEIGHT / 2.0, 1.0)
	wall_mat.roughness = 0.9

	# Four walls with a 2 m doorway in the north wall, so walking out of the light is
	# possible and shadow occlusion can be seen working.
	#
	# Each direction gets its own explicit position and size. The previous version reused
	# one `at`/`dim` pair and reassigned them per direction, which silently collapsed the
	# east and west walls onto the same corner (the diagnostic in tests/shot.gd caught two
	# StaticBody3D at identical global positions) and left a wall running diagonally across
	# the room. Explicit beats clever here.
	const WALL_T := 0.4
	for d in 4:
		var segments: Array = [[-HH, HH]]
		if d == 0:
			segments = [[-HH, -HH + 5.5], [-HH + 7.5, HH]]
		for seg in segments:
			var length: float = float(seg[1]) - float(seg[0])
			if length <= 0.01:
				continue
			var mid: float = (float(seg[0]) + float(seg[1])) * 0.5
			var at := Vector3.ZERO
			var dim := Vector3.ZERO
			match d:
				0:  # north (-Z)
					at = Vector3(mid, WALL_HEIGHT * 0.5, -HH)
					dim = Vector3(length, WALL_HEIGHT, WALL_T)
				1:  # east (+X)
					at = Vector3(HH, WALL_HEIGHT * 0.5, mid)
					dim = Vector3(WALL_T, WALL_HEIGHT, length)
				2:  # south (+Z)
					at = Vector3(mid, WALL_HEIGHT * 0.5, HH)
					dim = Vector3(length, WALL_HEIGHT, WALL_T)
				_:  # west (-X)
					at = Vector3(-HH, WALL_HEIGHT * 0.5, mid)
					dim = Vector3(WALL_T, WALL_HEIGHT, length)
			_slab(dim, at, wall_mat)

	# Props: the identity of the place. A room with one knight in it reads as a test box; the
	# abbey has to be furnished before the look can be judged at all.
	# Prop heights are in metres and chosen so each reads at its real-world size: a pillar
	# is ceiling height, an altar is waist height, a candle rack is shoulder height. Art is
	# scaled to the world, never the other way round.
	for spec in [
		["altar", Vector3(2.6, 0.0, -3.4), 1.1],
		["candle_rack", Vector3(-3.2, 0.0, -1.2), 1.6],
		["candle_rack", Vector3(3.6, 0.0, 1.6), 1.6],
		["candle_rack", Vector3(-1.4, 0.0, 4.4), 1.6],
		["reliquary", Vector3(-2.8, 0.0, 3.2), 0.9],
		["pillar", Vector3(-HH + 1.2, 0.0, -HH + 1.2), 3.4],
		["pillar", Vector3(HH - 1.2, 0.0, -HH + 1.2), 3.4],
		["pillar", Vector3(-HH + 1.2, 0.0, HH - 1.2), 3.4],
		["pillar", Vector3(HH - 1.2, 0.0, HH - 1.2), 3.4],
		["banner", Vector3(HH - 0.3, 0.6, 2.0), 2.4],
		["banner", Vector3(HH - 0.3, 0.6, -1.0), 2.4],
		["banner", Vector3(-HH + 0.3, 0.6, 0.5), 2.4],
		["sigil", Vector3(0.0, 0.0, 1.2), 0.0],
	]:
		var kind := str(spec[0])
		var at: Vector3 = spec[1]
		var world_h := float(spec[2])
		if kind == "sigil":
			# A floor decal, not a standing billboard: flat on the ground.
			_sigil(at)
			continue
		# Standing props are anchored by their feet, exactly like figures: the position is
		# where they touch the floor, not their centre.
		_sprite3d("res://assets/props/%s.png" % kind, at, world_h, true, "feet")


## Floor sigil: a flat quad lying on the ground, so the ritual circle is part of the floor
## rather than a billboard standing in the middle of the room.
func _sigil(at: Vector3) -> void:
	if not ResourceLoader.exists("res://assets/props/sigil.png"):
		return
	var decal := Sprite3D.new()
	decal.texture = load("res://assets/props/sigil.png")
	decal.pixel_size = 4.0 / float(decal.texture.get_width())
	decal.position = at + Vector3(0.0, 0.03, 0.0)
	# Blender-style coordinate note: rotating -90 about X lays a sprite flat, which is why
	# this is the one sprite in the scene that is NOT billboarded.
	decal.rotation_degrees = Vector3(-90, 0, 0)
	decal.modulate = Color(0.85, 0.8, 0.75, 0.85)
	decal.shaded = false
	decal.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	add_child(decal)


func _slab(dim: Vector3, at: Vector3, mat: Material) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = dim
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.material_override = mat
	node.position = at
	add_child(node)
	# Walls and floor occlude light; a prop box does not need its own collider here
	# because the knight collides with the room, not with furniture, in this slice.
	if dim.y > 0.5:
		var body := StaticBody3D.new()
		var col := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = dim
		col.shape = shape
		body.add_child(col)
		body.position = at
		add_child(body)
	return node


# ---------------------------------------------------------------------------------------
# actors
# ---------------------------------------------------------------------------------------

## A standing sprite, anchored by its FEET at `at`.
##
## Sprite3D draws its quad centred on the node origin, so a sprite placed at floor level
## would be half sunk into it. `offset` is in the sprite quad's own pixels and positive Y
## moves the sprite UP, so pushing it up by half the frame height puts the bottom edge on
## the floor. Single-frame props are `vframes = 1`, so "frame height" is just texture
## height — getting this wrong is what buried the knight in the floor in prototype #1.
##
## `pivot` selects what `at` means: "feet" for anything standing on the ground (a pillar, a
## candle rack, a knight) and "centre" for anything already measured to its middle. Getting
## this wrong is subtle — the prop still renders, it just floats — so it is named rather
## than assumed.
func _sprite3d(path: String, at: Vector3, world_h: float, shadow: bool,
		pivot: String = "feet") -> Sprite3D:
	var s := Sprite3D.new()
	if ResourceLoader.exists(path):
		s.texture = load(path)
	else:
		push_warning("missing asset: %s" % path)
	if s.texture == null:
		return s
	var frame_h := float(s.texture.get_height() / maxi(1, s.vframes))
	s.pixel_size = world_h / frame_h
	s.offset = Vector2(0.0, frame_h * 0.5 if pivot == "feet" else 0.0)
	s.position = at + (Vector3(0.0, world_h * 0.5, 0.0) if pivot == "centre" else Vector3.ZERO)
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	s.shaded = true
	if shadow:
		# A contact shadow sells the object standing ON the floor rather than floating. It
		# is a separate quad rather than part of the sprite so it stays flat on the ground
		# regardless of the prop's height.
		var sh := Sprite3D.new()
		sh.texture = _shadow_texture()
		sh.pixel_size = world_h * 0.5 / 64.0
		var foot: Vector3 = at if pivot == "feet" else at - Vector3(0.0, world_h * 0.5, 0.0)
		sh.position = Vector3(foot.x, 0.02, foot.z)
		sh.rotation_degrees = Vector3(-90, 0, 0)
		sh.modulate = Color(0, 0, 0, 0.4)
		sh.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR
		add_child(sh)
	add_child(s)
	return s


func _shadow_texture() -> ImageTexture:
	var n := 64
	var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
	var c := (n - 1) / 2.0
	for y in n:
		for x in n:
			var d := Vector2(x - c, y - c).length() / c
			img.set_pixel(x, y, Color(1, 1, 1, clampf(1.0 - d, 0.0, 1.0) ** 2))
	return ImageTexture.create_from_image(img)


func _build_knight() -> void:
	knight = Node3D.new()
	knight.name = "Knight"
	add_child(knight)
	var s := Sprite3D.new()
	s.name = "Body"
	var path := "res://assets/characters/knight_walk/knight_walk.png"
	if ResourceLoader.exists(path):
		s.texture = load(path)
	s.hframes = 4
	s.vframes = 4
	s.frame = 0
	if s.texture:
		s.pixel_size = KNIGHT_M / float(s.texture.get_height() / 4)
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	s.shaded = true
	s.offset = Vector2(0.0, float(s.texture.get_height() / 4) * 0.5 if s.texture else 0.0)
	knight.add_child(s)
	var shadow := Sprite3D.new()
	shadow.texture = _shadow_texture()
	shadow.pixel_size = 1.0 / 32.0
	shadow.rotation_degrees = Vector3(-90, 0, 0)
	shadow.position = Vector3(0, 0.02, 0)
	shadow.modulate = Color(0, 0, 0, 0.5)
	knight.add_child(shadow)
	var body := CharacterBody3D.new()
	var col := CollisionShape3D.new()
	var shape := CapsuleShape3D.new()
	shape.radius = 0.32
	shape.height = 1.5
	col.shape = shape
	col.position = Vector3(0, 0.75, 0)
	body.add_child(col)
	body.name = "Collision"
	knight.add_child(body)


func _build_camera() -> void:
	camera = Camera3D.new()
	camera.name = "Camera"
	# Perspective, deliberately: see the header. The cost is that a tile is a few percent
	# larger at the bottom of the frame than at the top, so the density stops being one
	# number. The benefit is the room reads as a place with depth instead of a floor plan.
	camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	camera.fov = CAM_FOV
	camera.near = 0.05
	camera.far = 200.0
	camera.rotation_degrees = Vector3(_pitch_deg, 0, 0)
	add_child(camera)
	var rad := deg_to_rad(_pitch_deg)
	camera.position = knight.position + Vector3(0, -sin(rad) * _dist, cos(rad) * _dist)
	camera.make_current()


## Nominal pixels per metre at the focus plane, for the HUD and the tests. With a
## perspective camera this is the value at the centre of the frame; the frame edges differ
## by a few percent, and that is stated rather than hidden.
func ppm_at_focus() -> float:
	return VIEWPORT.y / (2.0 * _dist * tan(deg_to_rad(CAM_FOV * 0.5)))


func _build_light() -> void:
	# The lantern is the only light, and it is the composition: the reference look is a warm
	# core with everything outside it falling to near-black. A weak wide light produces the
	# flat grey wash the first frame had.
	lantern = SpotLight3D.new()
	lantern.name = "Lantern"
	lantern.light_color = TALLOW
	lantern.light_energy = 22.0
	lantern.spot_range = 16.0
	lantern.spot_angle = 58.0
	lantern.spot_angle_attenuation = 1.8
	lantern.spot_attenuation = 1.6
	lantern.shadow_enabled = true
	lantern.shadow_bias = 0.02
	lantern.rotation_degrees = Vector3(-90, 0, 0)
	lantern.position = Vector3(0.4, 2.7, 0.0)
	knight.add_child(lantern)

	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color("05050a")
	# Fog is how a 3D scene gets depth at this scale: it separates the near floor from the
	# far wall, which is what makes the room read as a room.
	e.fog_enabled = true
	e.fog_light_color = Color("101018")
	e.fog_density = 0.012
	e.fog_sky_affect = 0.0
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color("4a4a5e")
	# Shipped mood is dark; 0.55 is the inspection value so geometry and art stay visible
	# while the prototype is being built (F4 toggles).
	e.ambient_light_energy = 1.05
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	e.tonemap_exposure = 1.15
	e.tonemap_white = 6.0
	e.ssao_enabled = true
	e.ssao_radius = 1.4
	e.ssao_intensity = 2.2
	e.glow_enabled = true
	e.glow_intensity = 0.5
	e.glow_bloom = 0.05
	e.glow_hdr_threshold = 1.1
	env.environment = e
	add_child(env)
	_environment = e


func _build_hud() -> void:
	var layer := CanvasLayer.new()
	var box := VBoxContainer.new()
	box.position = Vector2(18, 14)
	_hud = Label.new()
	_hud.add_theme_color_override("font_color", Color(0.94, 0.88, 0.72))
	_hud.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	_hud.add_theme_constant_override("outline_size", 4)
	box.add_child(_hud)
	layer.add_child(box)
	add_child(layer)


## Print the numbers the style spec promises, MEASURED rather than assumed. If this line
## disagrees with the spec, the camera is wrong — do not adjust the art.
##
## The derivation, once, with the trig the right way round — and it was wrong twice before
## it was right. Measured on the live camera (see tests/shot.gd's CALIB lines), one metre of
## world along each axis projects to:
##     X (across the ground) : ppm
##     Z (into the ground)   : ppm * cos(pitch)
##     Y (height)            : ppm * cos(pitch)        <- NOT sin(pitch)
## X and Z are the ground plane; a metre of height is foreshortened by the SAME factor as a
## metre of depth, because they both lie in the plane the camera looks along. So:
##     figure_px = height_m * ppm * cos(pitch)
##     wall_px   = wall_m   * ppm * cos(pitch)
## Consequences, and they are not negotiable: a human figure cannot be large AND the camera
## shallow AND the walls visible. At 1.8 m and 42 px/m a knight is 44 px at 55 deg, 54 px at
## 45 deg, and 60 px at 38 deg — while the wall face falls from 78 px to 40 px over the same
## range. The project trades figure size for architecture, and 55 deg is that choice.
func _report_budget() -> void:
	var vp := get_viewport().get_visible_rect().size
	var pitch := deg_to_rad(absf(_pitch_deg))
	var ppm := ppm_at_focus()
	print("--- Iron Vigil camera budget ---")
	print("viewport            : %d x %d" % [vp.x, vp.y])
	print("projection          : perspective, fov %.0f deg at %.1f m" % [CAM_FOV, _dist])
	print("pitch               : %.0f deg" % _pitch_deg)
	print("px per floor metre  : %.2f at focus (nominal %.2f)" % [ppm, PPM])
	print("one tile on screen  : %.1f px at focus" % (ppm * TILE))
	print("ground visible      : %.1f m wide at focus (%.1f rooms of %d tiles)"
		% [vp.x / ppm, vp.x / ppm / ROOM_TILES, ROOM_TILES])
	print("height on screen    : %.1f px per metre of height (cos(pitch)=%.3f)"
		% [ppm * cos(pitch), cos(pitch)])
	print("knight on screen    : %.1f px  (%.2f m x %.1f px/m of height)"
		% [KNIGHT_M * ppm * cos(pitch), KNIGHT_M, ppm * cos(pitch)])
	print("wall face on screen : %.1f px for a %.1f m wall"
		% [WALL_HEIGHT * ppm * cos(pitch), WALL_HEIGHT])


# ---------------------------------------------------------------------------------------
# input / update
# ---------------------------------------------------------------------------------------

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F1:
			## A/B the projection so the claim in the spec can be seen, not trusted.
			camera.projection = (Camera3D.PROJECTION_PERSPECTIVE
				if camera.projection == Camera3D.PROJECTION_ORTHOGONAL
				else Camera3D.PROJECTION_ORTHOGONAL)
			print("projection -> %s" % ("perspective" if camera.projection == Camera3D.PROJECTION_PERSPECTIVE else "orthographic"))
		elif event.keycode == KEY_F2:
			lantern.visible = not lantern.visible
		elif event.keycode == KEY_F4:
			## The darkness A/B. Neither state is "wrong": 0.16 is the shipped mood, 0.85 is
			## the inspection state. Keeping both on one key stops the mood from silently
			## becoming the thing that hides bugs.
			_ambient_lit = not _ambient_lit
			if _environment:
				_environment.ambient_light_energy = 1.05 if _ambient_lit else 0.22
			print("ambient -> %s" % ("inspection 0.85" if _ambient_lit else "shipped 0.16"))
		elif event.keycode == KEY_F3:
			Input.mouse_mode = (Input.MOUSE_MODE_VISIBLE
				if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED)
		elif event.keycode == KEY_ESCAPE:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _physics_process(delta: float) -> void:
	var body := knight.get_node("Collision") as CharacterBody3D
	# Screen-space movement: up on screen is forward in the world at this camera pitch,
	# so the room is never rotated underneath the player.
	var input := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	var dir := Vector3(input.x, 0.0, input.y).normalized()
	body.velocity = dir * KNIGHT_SPEED
	body.move_and_slide()
	knight.position.x = body.position.x
	knight.position.z = body.position.z
	var sprite := knight.get_node("Body") as Sprite3D
	if dir.length_squared() > 0.01:
		var facing := 0 if dir.z > 0.5 else (3 if dir.z < -0.5 else (1 if dir.x < 0.0 else 2))
		sprite.frame = facing * 4 + int(Time.get_ticks_msec() / 150.0) % 4
	else:
		sprite.frame = 0


func _process(delta: float) -> void:
	# Follow with a lag so movement reads as motion rather than the world sliding.
	var rad := deg_to_rad(_pitch_deg)
	camera.position = camera.position.lerp(
		knight.position + Vector3(0, -sin(rad) * _dist, cos(rad) * _dist),
		clampf(delta * CAM_FOLLOW, 0.0, 1.0))
	_frames += 1
	if _hud and _frames % 15 == 0:
		var pitch := deg_to_rad(absf(_pitch_deg))
		var ppm := ppm_at_focus()
		_hud.text = ("Iron Vigil  ·  技术原型\n"
			+ "WASD 移动    F1 正投影/透视    F2 灯    F3 鼠标    F4 环境光    Esc 释放\n"
			+ "%.0f px/格   骑士 %.0f px   墙高 %.0f px   一屏 %.1f 间房"
			% [ppm, KNIGHT_M * ppm * cos(pitch), WALL_HEIGHT * ppm * cos(pitch),
				VIEWPORT.x / ppm / ROOM_TILES])
