"""
Локальне перевизначення рецепту opencv для python-for-android.

ІСТОРІЯ: рецепт opencv у p4a v2024.01.21 накладає patches/p4a_build.patch
(написаний під OpenCV 4.0.1, 2019 рік) на джерельний код OpenCV. Патч
робить лише ТРИ маленькі текстові зміни - додає умову `P4A OR ...` у
двох CMake-файлах, щоб OpenCV не вимикав збірку Python-біндингів
(cv2.so) під час збірки для Android (за замовчуванням OpenCV вважає,
що Android-збірка = Java/JNI, і Python-біндинги там не потрібні).

Коли підіймаємо версію OpenCV до 4.9.0 (потрібно для коректної роботи
cv2.dnn з YOLOv8 ONNX - див. https://github.com/ultralytics/yolov3/issues/1798,
той самий баг ще на 4.5.2), патч більше не накладається через `patch`
(контекст навколо змінених рядків розійшовся за 5 років розвитку
OpenCV) - навіть з --fuzz=5.

РІШЕННЯ: замість format-diff патчу робимо ПРЯМУ текстову заміну тих
самих трьох рядків. Сам синтаксис цих умов - базовий, стабільний CMake,
що не змінювався роками, тож текст рядків, які треба замінити,
з високою ймовірністю ідентичний і в 4.9.0, незалежно від того, на
яких саме номерах рядків він тепер знаходиться.
"""

import os

from pythonforandroid.recipes.opencv import OpenCVRecipe as _OpenCVRecipe


# (відносний_шлях_до_файлу, що_шукаємо, на_що_замінюємо)
REPLACEMENTS = [
    (
        # Підтверджено з реального файлу в OpenCV 4.9.0 (grep -n -i "android" ...):
        # умова виросла з "if(NOT ANDROID AND NOT IOS)" (2019) до
        # "if(NOT ANDROID AND NOT IOS AND NOT XROS)" (додалась підтримка
        # Apple Vision Pro), той самий логічний блок, просто новіший.
        "cmake/OpenCVDetectPython.cmake",
        "if(NOT ANDROID AND NOT IOS AND NOT XROS)",
        "if(P4A OR NOT ANDROID AND NOT IOS AND NOT XROS)",
    ),
    (
        "cmake/OpenCVDetectPython.cmake",
        "endif(NOT ANDROID AND NOT IOS AND NOT XROS)",
        "endif(P4A OR NOT ANDROID AND NOT IOS AND NOT XROS)",
    ),
    (
        "modules/python/CMakeLists.txt",
        "if(ANDROID OR APPLE_FRAMEWORK OR WINRT)",
        "if(ANDROID AND NOT P4A OR APPLE_FRAMEWORK OR WINRT)",
    ),
]


class OpenCVRecipe(_OpenCVRecipe):

    def apply_patches(self, arch, build_dir=None):
        build_dir = build_dir or self.get_build_dir(arch.arch)

        for rel_path, search_text, replace_text in REPLACEMENTS:
            file_path = os.path.join(build_dir, rel_path)

            if not os.path.exists(file_path):
                print(f"[local opencv recipe] УВАГА: файл не знайдено: {file_path}")
                continue

            with open(file_path, "r") as f:
                content = f.read()

            if replace_text in content:
                print(f"[local opencv recipe] {rel_path}: заміна вже застосована, пропускаю")
                continue

            if search_text not in content:
                print(
                    f"[local opencv recipe] ПОМИЛКА: не знайдено очікуваний "
                    f"текст у {rel_path}: {search_text!r}"
                )
                continue

            content = content.replace(search_text, replace_text)

            with open(file_path, "w") as f:
                f.write(content)

            print(f"[local opencv recipe] {rel_path}: замінено {search_text!r} -> {replace_text!r}")


recipe = OpenCVRecipe()