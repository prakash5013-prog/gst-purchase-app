[app]
title = GST Purchase Report
package.name = gst_purchase
package.domain = org.yourcompany
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,ttf,md
requirements = python3,kivy,kivymd,plyer,sqlite3,android,pyjnius
orientation = portrait
fullscreen = 0
log_level = 1
android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.permissions = READ_MEDIA_IMAGES, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE
[buildozer]
log_level = 2
warn_on_root = 1
