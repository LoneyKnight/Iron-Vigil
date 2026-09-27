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
