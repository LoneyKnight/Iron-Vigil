extends CharacterBody3D
## A cultist: wanders near where it was left, chases what it sees, hits what it touches.
##
## "Sees" means line of sight and nothing more. No hearing, no memory, no pack behaviour —
## those belong to the identity systems (sound as a resource, the house waking up) that sit
## on top of this loop, and faking them now would make the loop harder to read.

signal struck(target_hp: int)

const SPEED_WANDER := 1.1
const SPEED_CHASE := 3.2
const SPEED_INVESTIGATE := 2.1
const SIGHT := 6.0
const TOUCH_RANGE := 1.05
const HIT_DAMAGE := 12
const HIT_INTERVAL := 1.1
const MAX_HP := 100
const SPRITE_H := 1.75
## How long it keeps walking toward a noise it did not find anything at, and how close it has
## to get before it gives up. Both matter: an investigator that never gives up turns the game
## into a chase, and one that forgets instantly makes noise pointless.
const INVESTIGATE_GIVE_UP := 7.0
const INVESTIGATE_ARRIVE := 1.2

enum State { WANDER, INVESTIGATE, CHASE }

var hp := MAX_HP
var alive := true
var state := State.WANDER

var _home := Vector3.ZERO
var _target: Node3D
var _wander_to := Vector3.ZERO
var _wander_t := 0.0
var _hit_cd := 0.0
var _sprite: Sprite3D
var _investigate_at := Vector3.ZERO
var _investigate_t := 0.0
var _chant_cd := 0.0


func setup(home: Vector3) -> void:
	_home = home
	position = home
	_wander_to = home


## It heard something. This is the whole point of the sound system: a noise the player made
## pulls the opposition across the map, so making one is a decision rather than a side effect.
##
## `threat` scales with how loud the source was, and the caller has already decided this
## cultist is within earshot.
func hear_noise(at: Vector3, threat: float) -> void:
	if not alive or state == State.CHASE:
		return
	_investigate_at = at
	_investigate_t = INVESTIGATE_GIVE_UP * clampf(0.6 + threat / 14.0, 0.6, 1.6)
	if state != State.INVESTIGATE:
		state = State.INVESTIGATE
		Sound.play("cultist_alert", global_position, 0.0)


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
	_chant_cd -= delta

	# Sight wins over hearing, and losing sight does not mean forgetting: the last seen
	# position becomes an investigate target, which is what makes breaking line of sight
	# useful without making it an instant escape.
	var seen := _visible_target()
	if seen != null:
		if state != State.CHASE:
			Sound.play("cultist_alert", global_position, 0.0)
		state = State.CHASE
		_investigate_at = seen.global_position
		_investigate_t = INVESTIGATE_GIVE_UP
		_steer(seen.global_position, SPEED_CHASE, delta)
		if global_position.distance_to(seen.global_position) <= TOUCH_RANGE and _hit_cd <= 0.0:
			_hit_cd = HIT_INTERVAL
			seen.take_damage(HIT_DAMAGE)
			struck.emit(seen.hp)
		return

	if state == State.CHASE:
		# Lost them. Go and look where they were.
		state = State.INVESTIGATE
		_investigate_t = INVESTIGATE_GIVE_UP

	if state == State.INVESTIGATE:
		_investigate_t -= delta
		if global_position.distance_to(_investigate_at) <= INVESTIGATE_ARRIVE or _investigate_t <= 0.0:
			state = State.WANDER
			_wander_to = _home
		else:
			_steer(_investigate_at, SPEED_INVESTIGATE, delta)
			return

	# Idle chant: the sound that tells the player something is in the next room before they can
	# see it. It is the reason the world feels inhabited rather than populated.
	if _chant_cd <= 0.0:
		_chant_cd = randf_range(6.0, 14.0)
		Sound.play("cultist_chant", global_position, 0.0, randf_range(0.94, 1.06))

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
	Sound.play("hit_flesh", global_position, 6.0)
	# Being hit is loud, and it pulls the cultist straight onto whoever hit it: violence is the
	# noisiest thing in the game, so it is always a trade rather than a free option.
	_investigate_at = global_position
	state = State.CHASE
	# A visible flinch: without any feedback a hit is indistinguishable from a miss, and the
	# player cannot tell whether they are in range.
	var tw := create_tween()
	tw.tween_property(_sprite, "modulate", Color(1.6, 0.7, 0.7), 0.05)
	tw.tween_property(_sprite, "modulate", Color(1, 1, 1), 0.18)
	if hp == 0:
		alive = false
		Sound.play("cultist_die", global_position, 10.0)
		tw.finished.connect(queue_free)
