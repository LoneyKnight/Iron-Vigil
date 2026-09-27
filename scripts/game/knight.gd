extends CharacterBody3D
## The player's knight: movement, the swing, and health.
##
## Deliberately thin. It answers "where am I, what am I facing, am I alive" and nothing else.
## Relics, run state and win conditions live on the run, because they outlive any one actor
## and are exactly the things a second player would later need to have replicated.

signal died
signal swung(at: Vector3, facing: Vector3)

const SPEED := 4.6                 # m/s: a walk, not a sprint, so rooms feel like rooms
const SPRITE_H := 1.80             # world height that lands on the 128 px design target
const SWING_TIME := 0.35
const SWING_REACH := 1.9
const MAX_HP := 100

var hp := MAX_HP
var alive := true
var facing := Vector3(0, 0, 1)     # unit vector on the ground plane
var sprite: Sprite3D
var body: CollisionShape3D         # named so callers and tests can find it
var lantern: SpotLight3D

var _swing_t := 0.0
var _swing_hits: Array = []        # ids already hit by the current swing
var _walk_t := 0.0
var _depth_scale := 1.0


func _ready() -> void:
	body = CollisionShape3D.new()
	body.name = "Collision"
	var cap := CapsuleShape3D.new()
	cap.radius = 0.34
	cap.height = 1.5
	body.shape = cap
	body.position = Vector3(0, 0.75, 0)
	add_child(body)

	sprite = Sprite3D.new()
	sprite.name = "Body"
	var path := "res://assets/characters/knight_walk/knight_walk.png"
	if ResourceLoader.exists(path):
		sprite.texture = load(path)
	if sprite.texture:
		sprite.hframes = 4
		sprite.vframes = 4
		var frame_h := float(sprite.texture.get_height() / 4)
		sprite.pixel_size = SPRITE_H / frame_h
		# A figure stands ON its origin: offset is in quad pixels, positive moves it up, so
		# half a frame lifts the feet from the origin to the floor.
		sprite.offset = Vector2(0.0, frame_h * 0.5)
	sprite.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	sprite.shaded = true
	add_child(sprite)

	var shadow := Sprite3D.new()
	shadow.texture = load("res://scripts/game/shadow_tex.gd").make()
	shadow.pixel_size = SPRITE_H * 0.55 / 64.0
	shadow.rotation_degrees = Vector3(-90, 0, 0)
	shadow.position = Vector3(0, 0.02, 0)
	shadow.modulate = Color(0, 0, 0, 0.45)
	shadow.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR
	add_child(shadow)

	motion_mode = CharacterBody3D.MOTION_MODE_FLOATING

	# The lantern. It is not decoration: it is the only real light in the game, it is what
	# makes a dark room readable, and it is what casts the shadows that tell the player
	# something is standing behind them. Attached to the knight because it belongs to the
	# knight — a light in the scene would be a light the player cannot move.
	lantern = SpotLight3D.new()
	lantern.name = "Lantern"
	lantern.light_color = Color("ffc46e")
	lantern.light_energy = 16.0
	lantern.spot_range = 16.0
	# A hand-held lantern lights the ground around the bearer, not the wall ahead of him. The
	# two failure modes are both easy to hit and both look wrong in a pitched view: aim it
	# forward and the knight is a silhouette against a lit door with the room in black; aim it
	# down with a wide cone and it paints a bright ring around his feet. It hangs slightly
	# behind and above, tilted just past vertical.
	lantern.spot_angle = 52.0
	lantern.spot_angle_attenuation = 1.9
	lantern.spot_attenuation = 1.4
	lantern.shadow_enabled = true
	lantern.shadow_bias = 0.03
	lantern.rotation_degrees = Vector3(-104.0, 0.0, 0.0)
	lantern.position = Vector3(0.28, 2.3, -0.35)
	add_child(lantern)

	# A dim warm pool at the feet, so the player is never a silhouette on a black floor and
	# can always see the ground they are standing on. Very low energy on purpose: it must not
	# compete with the lantern, only stop the floor under the player from going pure black.
	var pool := OmniLight3D.new()
	pool.name = "Footpool"
	pool.light_color = Color("ffcf8a")
	pool.light_energy = 3.2
	pool.omni_range = 4.2
	pool.omni_attenuation = 1.8
	pool.position = Vector3(0, 1.1, 0)
	pool.shadow_enabled = false
	add_child(pool)


## Movement speed has to be equal in every screen direction. A pitched camera compresses
## depth on screen, so one metre walked "up the screen" covers less world distance than one
## metre walked sideways; without this correction, walking away is slower than walking
## across, and in a game where distance and time matter that is a real bug rather than a
## detail. The run injects cos(pitch) once, so the actor never needs to know about cameras.
func apply_depth_scale(cos_pitch: float) -> void:
	_depth_scale = maxf(cos_pitch, 0.2)


## Point the body at the ground position under the mouse. The camera is pitched, so the
## screen-to-ground mapping is not the trivial one: only the ground projection of the
## camera ray is meaningful for something walking on a floor.
func face_mouse(camera: Camera3D, mouse: Vector2) -> void:
	var near := camera.project_position(mouse, 0.0)
	var far := camera.project_position(mouse, 30.0)
	var dir := far - near
	dir.y = 0.0
	if dir.length_squared() > 0.0001:
		facing = dir.normalized()


func _physics_process(delta: float) -> void:
	if not alive:
		velocity = Vector3.ZERO
		move_and_slide()
		return
	var input := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	# Screen-relative movement: W walks away from the camera wherever the body is facing.
	# That is what the hand expects under a fixed camera, and it is why the camera never
	# rotates.
	velocity = Vector3(input.x, 0.0, input.y * _depth_scale).normalized() * SPEED
	move_and_slide()
	_swing_t = maxf(0.0, _swing_t - delta)
	_update_frame(delta)


func swing() -> bool:
	if not alive or _swing_t > 0.0:
		return false
	_swing_t = SWING_TIME
	_swing_hits.clear()
	swung.emit(global_position, facing)
	return true


func swing_active() -> bool:
	return _swing_t > 0.0


func already_hit(id: int) -> bool:
	return id in _swing_hits


func mark_hit(id: int) -> void:
	_swing_hits.append(id)


func take_damage(amount: int) -> void:
	if not alive:
		return
	hp = maxi(0, hp - amount)
	if hp == 0:
		alive = false
		died.emit()


func _update_frame(delta: float) -> void:
	if sprite == null or sprite.texture == null:
		return
	var moving := velocity.length() > 0.2
	# The sheet rows are down / left / right / up.
	var row := 0
	if absf(facing.x) > absf(facing.z):
		row = 1 if facing.x < 0.0 else 2
	else:
		row = 3 if facing.z < 0.0 else 0
	var col := 0
	if moving:
		_walk_t += delta * 9.0
		col = int(_walk_t) % 4
	else:
		_walk_t = 0.0
	sprite.frame = row * 4 + col
