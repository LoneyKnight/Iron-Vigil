extends RefCounted
## A soft radial blob, used as a contact shadow under every standing thing.
##
## Procedural on purpose: it is one channel of alpha with no detail, so shipping it as a PNG
## would mean an import settings file to keep in sync for no benefit.

static func make(size: int = 64) -> ImageTexture:
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var c := (size - 1) * 0.5
	for y in size:
		for x in size:
			var d := Vector2(x - c, y - c).length() / c
			img.set_pixel(x, y, Color(1, 1, 1, clampf(1.0 - d, 0.0, 1.0) ** 2))
	return ImageTexture.create_from_image(img)
