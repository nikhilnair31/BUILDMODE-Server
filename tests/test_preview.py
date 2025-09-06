# test_preview.py

from linkpreview import link_preview

preview = link_preview("https://sharif.io/28-ideas-2025")
print("title:", preview.title)
print("description:", preview.description)
print("image:", preview.image)
print("force_title:", preview.force_title)
print("absolute_image:", preview.absolute_image)
print("site_name:", preview.site_name)
print("favicon:", preview.favicon)
print("absolute_favicon:", preview.absolute_favicon)