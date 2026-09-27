extends CharacterBody3D
## A cultist: wanders near where it was left, chases what it sees, hits what it touches.
##
## "Sees" means line of sight and nothing more. No hearing, no memory, no pack behaviour —
## those belong to the identity systems (sound as a resource, the house waking up) that sit
## on top of this loop, and faking them now would make the loop harder to read.

signal struck(target_hp: int)

const SPEED_WANDER := 1.1
const SPEED_CHASE := 3.2
const SIGHT := 6.0
const TOUCH_RANGE := 1.05
const HIT_DAMAGE := 12
const HIT_INTERVAL := 1.1
const MAX_HP := 100
const SPRITE_H := 1.75

var hp := MAX_HP
var alive := true

var _home := Vector3.ZERO
var _target: Node3D
var _wander_to := Vector3.ZERO
var _wander_t := 0.0
var _hit_cd := 0.0
var _sprite: Sprite3D


func setup(home: Vector3) -> void:
	_home = home
	position = home
	_wander_to = home


func _ready() -> void:
	var col := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.32
	cap.height = 1.5
	col.shape = cap
	col.position = Vector3(0, 0.75, 0)
	add_child(col)

	_sprite = Sprite3D.new()
	var path := "res://assets/enemies/cultist/cultist.png"
	if ResourceLoader.exists(path):
		_sprite.texture = load(path)
	if _sprite.texture:
		_sprite.hframes = 4
		_sprite.vframes = 4
		var frame_h := float(_sprite.texture.get_height() / 4)
		_sprite.pixel_size = SPRITE_H / frame_h
		_sprite.offset = Vector2(0.0, frame_h * 0.5)
	_sprite.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	_sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	_sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	_sprite.shaded = true
	add_child(_sprite)

	motion_mode = CharacterBody3D.MOTION_MODE_FLOATING


func set_target(t: Node3D) -> void:
	_target = t


func _physics_process(delta: float) -> void:
	if not alive:
		return
	_hit_cd = maxf(0.0, _hit_cd - delta)

	var seen := _visible_target()
	if seen != null:
		_steer(seen.global_position, SPEED_CHASE, delta)
		if global_position.distance_to(seen.global_position) <= TOUCH_RANGE and _hit_cd <= 0.0:
			_hit_cd = HIT_INTERVAL
			seen.take_damage(HIT_DAMAGE)
			struck.emit(seen.hp)
	else:
		_wander_t -= delta
		if _wander_t <= 0.0 or global_position.distance_to(_wander_to) < 0.4:
			_wander_t = randf_range(1.6, 3.4)
			var a := randf() * TAU
			var r := randf_range(0.8, 2.2)
			_wander_to = _home + Vector3(cos(a) * r, 0.0, sin(a) * r)
		_steer(_wander_to, SPEED_WANDER, delta)


func _visible_target() -> Node3D:
	if _target == null or not is_instance_valid(_target):
		return null
	if not bool(_target.get("alive")):
		return null
	var to: Vector3 = _target.global_position - global_position
	if to.length() > SIGHT:
		return null
	# Line of sight only: a cultist does not see through a wall, and with the walls built as
	# real colliders the cheapest honest test is a ray.
	var space := get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(
		global_position + Vector3(0, 1.0, 0), _target.global_position + Vector3(0, 1.0, 0))
	q.exclude = [get_rid()]
	var hit := space.intersect_ray(q)
	return _target if hit.is_empty() or hit.collider == _target else null


func _steer(to: Vector3, speed: float, _delta: float) -> void:
	var dir := to - global_position
	dir.y = 0.0
	if dir.length_squared() < 0.0001:
		velocity = Vector3.ZERO
	else:
		velocity = dir.normalized() * speed
		_face(dir)
	move_and_slide()
	_bob()


func _face(dir: Vector3) -> void:
	if _sprite == null or _sprite.texture == null:
		return
	var row := 0
	if absf(dir.x) > absf(dir.z):
		row = 1 if dir.x < 0.0 else 2
	else:
		row = 3 if dir.z < 0.0 else 0
	_sprite.frame = row * 4 + (int(Time.get_ticks_msec() / 160.0) % 4)


func _bob() -> void:
	if _sprite and _sprite.texture:
		pass


func take_damage(amount: int) -> void:
	if not alive:
		return
	hp = maxi(0, hp - amount)
	# A visible flinch: without any feedback a hit is indistinguishable from a miss, and the
	# player cannot tell whether they are in range.
	var tw := create_tween()
	tw.tween_property(_sprite, "modulate", Color(1.6, 0.7, 0.7), 0.05)
	tw.tween_property(_sprite, "modulate", Color(1, 1, 1), 0.18)
	if hp == 0:
		alive = false
		tw.finished.connect(queue_free)
