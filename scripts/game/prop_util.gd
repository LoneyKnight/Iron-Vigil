extends RefCounted
## Shared builders for the interactive props. Three of them need a box with a material and a
## proximity sensor, and duplicating that three times is how the geometry drifts apart.
##
## Static so callers never need an instance: `PropUtil.box(self, ...)`.

const INK := Color("16130f")
const IRON := Color("3a3a3e")
const OAK := Color("4a3423")
const OAK_DARK := Color("2e2015")
const STONE := Color("6a665c")
const STONE_DARK := Color("4a4741")
const TALLOW := Color("ffc46e")
const OXBLOOD := Color("5a1e1e")


static func mat(colour: Color, rough: float = 0.9) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = colour
	m.roughness = rough
	return m


static func box(parent: Node3D, size: Vector3, at: Vector3, material: Material) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	var n := MeshInstance3D.new()
	n.mesh = mesh
	n.material_override = material
	n.position = at
	parent.add_child(n)
	return n


## Blocks passage. Kept separate from `box` because a prop that stops the player and a prop
## that does not are different things, and only one of them should be invisible in the code.
static func blocker(parent: Node3D, size: Vector3, at: Vector3 = Vector3.ZERO) -> StaticBody3D:
	var body := StaticBody3D.new()
	var col := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	col.shape = shape
	body.add_child(col)
	body.position = at
	parent.add_child(body)
	return body


## Proximity sensor. The radius is generous on purpose: making the player line up exactly is
## not difficulty, it is friction, and the prompt is what tells them they are close enough.
static func sensor(parent: Node3D, radius: float) -> Area3D:
	var a := Area3D.new()
	var c := CollisionShape3D.new()
	var s := SphereShape3D.new()
	s.radius = radius
	c.shape = s
	a.add_child(c)
	a.monitoring = true
	parent.add_child(a)
	return a


## A soft warm light, for the things that should be noticeable before they are reachable.
static func glow(parent: Node3D, at: Vector3, energy: float, radius: float) -> OmniLight3D:
	var l := OmniLight3D.new()
	l.light_color = TALLOW
	l.light_energy = energy
	l.omni_range = radius
	l.position = at
	l.shadow_enabled = false
	parent.add_child(l)
	return l


## A standing prop sprite, anchored by its feet at `at`.
##
## Scaling is by HEIGHT by default, and that is wrong for anything whose width is the thing
## that must match the world — a door, for instance, whose art is 2.28 m tall by 1.60 m wide
## while its opening is 2.6 m by 1.6 m. Scaling that by height would make it 1.82 m wide and
## overlap the wall on both sides. `width_m` selects width-locked scaling instead; the height
## then follows from the art's aspect and is allowed to differ from the opening, because a
## 2.29 m door in a 2.6 m opening is simply a door with a frame above it.
##
## Returns null when the asset is not there, and every caller treats that as "build the box
## version instead". That is deliberate and permanent: it keeps the game runnable while art is
## being generated, and it means a missing file degrades the look rather than breaking the run.
static func sprite(parent: Node3D, asset: String, at: Vector3, world_h: float,
		width_m: float = 0.0) -> Sprite3D:
	if not ResourceLoader.exists(asset):
		return null
	var tex: Texture2D = load(asset)
	if tex == null:
		return null
	var s := Sprite3D.new()
	s.texture = tex
	if width_m > 0.0:
		s.pixel_size = width_m / float(maxi(1, tex.get_width()))
	else:
		s.pixel_size = world_h / float(maxi(1, tex.get_height()))
	# Positive offset moves the sprite UP; half the drawn height puts its bottom edge on the
	# floor. Computed from the texture, so it is right under either scaling rule.
	s.offset = Vector2(0.0, float(tex.get_height()) * 0.5)
	s.position = at
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	s.shaded = true
	parent.add_child(s)
	return s


## A contact shadow: a flat quad on the ground, so the prop reads as standing ON the floor
## instead of floating over it.
static func contact_shadow(parent: Node3D, at: Vector3, radius: float,
		alpha: float = 0.4) -> Sprite3D:
	var s := Sprite3D.new()
	s.texture = load("res://scripts/game/shadow_tex.gd").make()
	s.pixel_size = radius / 32.0
	s.position = Vector3(at.x, 0.02, at.z)
	s.rotation_degrees = Vector3(-90, 0, 0)
	s.modulate = Color(0, 0, 0, alpha)
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR
	parent.add_child(s)
	return s
