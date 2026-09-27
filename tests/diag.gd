extends Node
## Diagnostic for "the props and the knight do not render at shallow pitch".
##
##   godot --path . -- --diag --pitch=36
##
## Prints only facts: what exists in the tree, where it projects on screen, and what the
## camera actually is. No assertions — this exists to replace guessing with one readout.

var run: Node3D
var _done := false


func _ready() -> void:
	var wd := Timer.new()
	wd.wait_time = 30.0
	wd.one_shot = true
	wd.timeout.connect(func():
		if not _done:
			print("DIAG: timed out")
			get_tree().quit(1))
	add_child(wd)
	wd.start()
	_go.call_deferred()


func _frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _find(node: Node) -> Node3D:
	for c in node.get_children():
		if c is Node3D and c.has_method("_report_budget"):
			return c as Node3D
		var f := _find(c)
		if f != null:
			return f
	return null


func _go() -> void:
	await _frames(8)
	run = _find(get_tree().root)
	if run == null:
		print("DIAG: run scene missing")
		get_tree().quit(1)
		return

	var cam: Camera3D = get_viewport().get_camera_3d()
	var vp := get_viewport().get_visible_rect().size
	print("DIAG camera: pos=%s rot=%s fov=%.1f near=%.3f far=%.1f proj=%d"
		% [cam.global_position, cam.global_rotation_degrees, cam.fov, cam.near, cam.far,
			cam.projection])
	print("DIAG camera: size=%.3f viewport=%s" % [cam.size, vp])
	print("DIAG knight: %s visible=%s" % [run.knight.global_position, run.knight.visible])

	# Every Sprite3D under the run, with the numbers that decide whether it can be seen.
	var sprites := _sprites(run)
	print("DIAG %d Sprite3D found" % sprites.size())
	for s in sprites:
		var g: Vector3 = s.global_position
		var behind: bool = cam.is_position_behind(g)
		var px: Vector2 = cam.unproject_position(g)
		var tex_h := 0.0
		if s.texture:
			tex_h = float(s.texture.get_height())
		var world_h: float = tex_h * s.pixel_size
		print("  %-22s global=%s pixel_size=%.5f tex=%s world_h=%.2f vframes=%d visible=%s"
			% [s.get_parent().name + "/" + s.name, g, s.pixel_size,
				str(s.texture.get_size()) if s.texture else "none", world_h, s.vframes,
				s.visible])
		print("      behind_cam=%s screen=%s alpha_cut=%d billboard=%d shaded=%s"
			% [behind, px, s.alpha_cut, s.billboard, s.shaded])

	print("DIAG mesh count: %d" % _count(run, "MeshInstance3D"))
	print("DIAG light count: %d" % _count(run, "Light3D"))

	_report_frame(cam, vp)

	# Framing sweep, in one process: the camera is a pure function of pitch/ppm, so several
	# candidate framings can be MEASURED here instead of rendered one process at a time. The
	# question "how much of the screen is the room, and how tall is the knight" is arithmetic
	# once the projection is known, and looking at four images to answer it is slower and
	# less precise.
	print("\nDIAG --- framing sweep (room %d m, %.1f m figure) ---"
		% [int(run.ROOM_TILES), float(run.KNIGHT_M)])
	print("DIAG %6s %6s %9s %9s %9s %9s" % ["pitch", "ppm", "room w%", "room h%", "knight px", "wall px"])
	for pitch in [34.0, 42.0, 50.0, 58.0]:
		for ppm in [42.0, 70.0, 100.0, 130.0]:
			cam.rotation_degrees = Vector3(-pitch, 0, 0)
			var dist: float = vp.y / (2.0 * ppm * tan(deg_to_rad(cam.fov * 0.5)))
			var rad := deg_to_rad(-pitch)
			cam.global_position = Vector3(0, -sin(rad) * dist, cos(rad) * dist)
			var r := _frame_rect(cam, vp)
			var knight_px: float = float(run.KNIGHT_M) * ppm * cos(deg_to_rad(pitch))
			var wall_px: float = float(run.WALL_HEIGHT) * ppm * cos(deg_to_rad(pitch))
			print("DIAG %6.0f %6.0f %8.1f%% %8.1f%% %9.0f %9.0f"
				% [pitch, ppm, r.x, r.y, knight_px, wall_px])

	_done = true
	get_tree().quit(0)


## Fraction of the viewport the room's floor rectangle covers at the current camera.
func _frame_rect(cam: Camera3D, vp: Vector2) -> Vector2:
	var half: float = float(run.HH)
	var xs: Array = []
	var ys: Array = []
	for p in [Vector3(-half, 0, -half), Vector3(half, 0, -half),
			Vector3(half, 0, half), Vector3(-half, 0, half)]:
		var s: Vector2 = cam.unproject_position(p)
		xs.append(s.x)
		ys.append(s.y)
	return Vector2((float(xs.max()) - float(xs.min())) / vp.x * 100.0,
		(float(ys.max()) - float(ys.min())) / vp.y * 100.0)


func _report_frame(cam: Camera3D, vp: Vector2) -> void:
	var half: float = float(run.HH)
	var pts := [Vector3(-half, 0, -half), Vector3(half, 0, -half),
		Vector3(half, 0, half), Vector3(-half, 0, half)]
	var xs: Array = []
	var ys: Array = []
	for p in pts:
		var s: Vector2 = cam.unproject_position(p)
		xs.append(s.x)
		ys.append(s.y)
	var w: float = float(xs.max()) - float(xs.min())
	var h: float = float(ys.max()) - float(ys.min())
	print("DIAG frame: room %.1f m -> %.0f x %.0f px = %.1f%% x %.1f%% of the screen"
		% [half * 2.0, w, h, w / vp.x * 100.0, h / vp.y * 100.0])


func _sprites(node: Node) -> Array:
	var out: Array = []
	for c in node.get_children():
		if c is Sprite3D:
			out.append(c)
		out.append_array(_sprites(c))
	return out


func _count(node: Node, cls: String) -> int:
	var n := 0
	for c in node.get_children():
		if c.is_class(cls):
			n += 1
		n += _count(c, cls)
	return n
