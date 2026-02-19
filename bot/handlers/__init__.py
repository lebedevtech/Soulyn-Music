# Этот файл заставляет Python считать папку handlers пакетом.
# 
# ⚠️ ПОРЯДОК ИМПОРТА ВАЖЕН!
# user_search должен импортироваться ПЕРЕД common,
# чтобы CommandStart(deep_link=True) зарегистрировался раньше 
# чем CommandStart() и правильно перехватывал deep link'и.

from . import user_search
from . import common
from . import playlists
from . import admin_menu