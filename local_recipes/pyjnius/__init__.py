"""
Локальне перевизначення рецепту pyjnius для python-for-android.

ПРИЧИНА: у "класичному" (pre-PyProjectRecipe) рецепті pyjnius є давній,
задокументований, ще не остаточно вирішений баг - файл jnius/config.pxi
(з визначеннями JNIUS_PLATFORM, JNIUS_PYTHON3 для Cython) генерується
власною логікою pyjnius/setup.py лише як побічний ефект спроби скомпілювати
jnius/src/org/jnius/NativeInvocationHandler.java. Якщо ця спроба не доходить
до кінця, config.pxi просто не з'являється, і подальша Cython-компіляція
валиться з помилками "'config.pxi' not found" /
"Compile-time name 'JNIUS_PLATFORM' not defined".

Див. https://github.com/kivy/buildozer/issues/1388
    https://github.com/kivy/python-for-android/issues/2790

РІШЕННЯ: пишемо jnius/config.pxi самі, у prebuild_arch(), ще ДО того,
як p4a запускає Cython - незалежно від того, чи спрацювала власна
логіка pyjnius. Значення 'android' і Python 3 тут завжди правильні для
наших цілей (Kivy на Android, Python 3), тож жодного автовизначення не
потрібно. JNIUS_CYTHON_3 = True, бо збірка йде на Cython >= 3.0.

ВАЖЛИВО: цей файл НЕ накладає жодних patch-файлів - на відміну від
local_recipes/opencv/__init__.py. Якщо в майбутньому побачиш тут
логіку зі спробами "sh.patch"/"--fuzz" - це помилково скопійований
код з opencv-рецепту, видали і постав назад цей варіант.
"""

from os.path import join

from pythonforandroid.recipes.pyjnius import PyjniusRecipe as _PyjniusRecipe


class PyjniusRecipe(_PyjniusRecipe):

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)

        config_pxi_path = join(
            self.get_build_dir(arch.arch), "jnius", "config.pxi"
        )

        with open(config_pxi_path, "w") as f:
            f.write('DEF JNIUS_PLATFORM = "android"\n')
            f.write("DEF JNIUS_PYTHON3 = True\n")
            f.write("DEF JNIUS_CYTHON_3 = True\n")

        print(f"[local pyjnius recipe] Записано {config_pxi_path}")


recipe = PyjniusRecipe()