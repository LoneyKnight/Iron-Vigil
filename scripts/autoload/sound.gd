extends Node
## Sound, and the noise it makes.
##
## This autoload exists for one design reason: in Iron Vigil a noise is not decoration, it is
## INFORMATION THAT EVERYONE SHARES. The player hears a cultist before seeing it, and — the
## other half, the half most games skip — the cultist hears the player. So every play call
## carries a position and a loudness, and the loudness is broadcast to whatever is listening.
##
## That is why the API is `play()` and not `play_at()`: there is no such thing as a sound that
## only the player hears. If a sound should be private (the heartbeat, a UI cue), it goes
## through `play_local()` and says so.
##
## Two facts from the previous project that are baked in here:
##   * every positional clip is MONO, because a stereo source fights the panner and destroys
##     the direction cue that this whole system exists to provide;
##   * a sound behind a wall goes through a low-pass bus, so "through the wall" is audibly
##     different from "in the room" without needing to see anything.

signal noise_made(at: Vector3, threat: float, kind: String, source: Node)

const SFX_DIR := "res://assets/sfx/"
const MUFFLED_BUS := "SFX_Muffled"
const SFX_BUS := "SFX"
## A wall between source and listener pushes the sound onto the muffled bus. The check is a
## single ray: with rooms this size, one hit is the whole answer, and more rays would only
## cost frames to refine a number the ear reads as "duller".
const MUFFLE_RAY_HEIGHT := 1.2

## How far a noise carries, in metres, per unit of threat. The absolute value matters less
## than the ratios: a slam must be heard across the building and a footstep must not.
const HEAR_PER_THREAT := 1.7

var listener: Node3D                      ## set by the run; the player's ears
var _players: Array[AudioStreamPlayer3D] = []
var _pool := 0
var _cache := {}


func set_listener(node: Node3D) -> void:
	listener = node


## Play a positional sound AND tell everything that can hear it that it happened.
##
## `threat` is the design knob: 0 = silent, 1 = a footstep, 14 = a door shouldered open. It
## controls both how loud it plays and how far it carries, so the two can never disagree.
##
## `source` is who caused it, and it exists so listeners can decide whether they care. A
## cultist's chant is a noise in the world that the player must hear; it is not a noise that
## should alert other cultists. Passing `self` is how a caller says "this was me".
func play(kind: String, at: Vector3, threat: float = 1.0,
		pitch: float = 1.0, volume_db: float = 0.0, source: Node = null) -> void:
	var stream := _stream(kind)
	if stream == null:
		return
	var p := _player()
	if p == null:
		return
	p.stream = stream
	p.global_position = at
	p.pitch_scale = pitch
	p.bus = MUFFLED_BUS if _behind_a_wall(at) else SFX_BUS
	var quiet := -6.0 * clampf(1.0 - threat / 14.0, 0.0, 1.0)
	p.volume_db = clampf(volume_db + quiet, -40.0, 6.0)
	p.play()
	if threat > 0.0:
		noise_made.emit(at, threat, kind, source)


## Sounds that are not in the world: the player's own heartbeat, UI feedback. Deliberately a
## separate call so that "only I can hear this" is always an explicit decision.
func play_local(kind: String, volume_db: float = 0.0) -> void:
	var stream := _stream(kind)
	if stream == null:
		return
	var p := AudioStreamPlayer.new()
	add_child(p)
	p.stream = stream
	p.bus = SFX_BUS
	p.volume_db = volume_db
	p.finished.connect(p.queue_free)
	p.play()


## Nearest listener distance, used by callers that want to scale a cue by proximity.
func distance_to_listener(at: Vector3) -> float:
	if listener == null or not is_instance_valid(listener):
		return INF
	return listener.global_position.distance_to(at)


func _stream(kind: String) -> AudioStream:
	if _cache.has(kind):
		return _cache[kind]
	var path := SFX_DIR + kind + ".wav"
	var s: AudioStream = load(path) if ResourceLoader.exists(path) else null
	if s == null:
		push_warning("sound: missing clip %s" % path)
	_cache[kind] = s
	return s


## A small rotating pool. Positional players are cheap but not free, and a footstep every
## 0.4 s for a whole run would otherwise allocate hundreds of nodes.
func _player() -> AudioStreamPlayer3D:
	if _players.size() < 16:
		var p := AudioStreamPlayer3D.new()
		p.max_distance = 60.0
		p.unit_size = 6.0
		p.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		add_child(p)
		_players.append(p)
		return p
	var p2 := _players[_pool]
	_pool = (_pool + 1) % _players.size()
	return p2


## True when something solid stands between the source and the listener, in which case the
## sound is routed through the low-pass bus.
func _behind_a_wall(at: Vector3) -> bool:
	if listener == null or not is_instance_valid(listener):
		return false
	var space := get_viewport().world_3d.direct_space_state if get_viewport() else null
	if space == null:
		return false
	var from := at + Vector3(0, MUFFLE_RAY_HEIGHT, 0)
	var to := listener.global_position + Vector3(0, MUFFLE_RAY_HEIGHT, 0)
	var q := PhysicsRayQueryParameters3D.create(from, to)
	# Only static geometry counts: a cultist standing between you and a door does not make the
	# door sound like it is in another room.
	q.collision_mask = 1
	var hit := space.intersect_ray(q)
	return not hit.is_empty()
