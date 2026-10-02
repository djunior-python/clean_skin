# Skin Detector

Android-застосунок для детекції проблемних ділянок шкіри обличчя
(темні кола під очима, пігментація, висипання тощо) на фото. Вся
обробка відбувається **повністю на пристрої**, без інтернету й
відправки зображень кудись назовні — inference іде локально через
OpenCV DNN.

## Як це працює

1. Користувач робить фото (системна камера) або обирає зображення з
   галереї.
2. Фото проганяється через модель детекції об'єктів (YOLOv8-nano,
   формат ONNX) напряму на пристрої.
3. Застосунок показує зображення з позначеними ділянками та список
   знайдених класів із рівнем впевненості.

## Класи детекції

Модель розпізнає 11 категорій:

`Dark Circle`, `Melasma`, `PIH`, `blackhead`, `freckles`, `nodule`
(включно з кістозними висипаннями), `papule`, `pustule`, `skin-pore`,
`whitehead`, `wrinkle`

## Технології

| Шар | Технологія |
|---|---|
| UI | [Kivy](https://kivy.org) 2.3.0 + [KivyMD](https://kivymd.readthedocs.io) 1.2.0 |
| Модель | YOLOv8-nano ([Ultralytics](https://github.com/ultralytics/ultralytics)), експортована в ONNX |
| Inference | OpenCV DNN (`cv2.dnn`), без сторонніх ML-рантаймів |
| Збірка під Android | [python-for-android](https://github.com/kivy/python-for-android) / [Buildozer](https://buildozer.readthedocs.io) |
| Камера/галерея | `plyer` + нативний Android `Intent` через `MediaStore` |

## Модель

- **Архітектура:** YOLOv8n — обрана свідомо (а не важча `s`/`m`) заради
  швидкого inference на мобільних процесорах без апаратного
  прискорення.
- **Датасет:** [Skin Detection](https://universe.roboflow.com/huyennguyen-wanak/skin-detection-pfmbg)
  (Roboflow Universe, ліцензія CC BY 4.0).
- **Підготовка даних:**
  - конвертація сегментаційної розмітки в bounding box;
  - фільтрація вироджених (аномально дрібних) анотацій;
  - виправлення розподілу train/valid/test — в оригінальному спліті
    датасету кілька класів (`skin-pore`, `Dark Circle`, `wrinkle`)
    були повністю відсутні у валідаційній/тестовій вибірці;
  - клас `cyst` об'єднано з `nodule` через критично малу кількість
    прикладів (3 зображення), що не дозволяло навчити його окремо.
- **Тренування:** 640×640, early stopping за `mAP50-95`, фінальний
  `mAP50-95 ≈ 0.13`, `mAP50 ≈ 0.32` на валідаційній вибірці.
- **Експорт:** ONNX, `opset=12` (обрано для сумісності з OpenCV DNN).
- **Рекомендований поріг впевненості:** `conf = 0.15` — нижче
  стандартних 0.25, бо помітно підвищує recall для дрібних класів
  (`blackhead`, `whitehead`, `pustule`) без суттєвої втрати точності.

### Відомі обмеження

- Дрібні, візуально неоднорідні класи (`blackhead`, `whitehead`,
  `wrinkle`) мають нижчий recall — це обмеження ємності nano-моделі
  та обсягу датасету, а не помилка пайплайну.
- Це **не медичний діагностичний інструмент**. Застосунок не замінює
  консультацію дерматолога.

## Структура проєкту

```
clean_skin/
├── main.py              # UI (KivyMD) + логіка камери/галереї
├── detector.py           # Обгортка над OpenCV DNN для inference ONNX-моделі
├── best.onnx              # Вага моделі
├── buildozer.spec
├── local_recipes/
│   ├── opencv/            # Патч для Python-біндингів OpenCV під Android
│   └── pyjnius/           # Фікс генерації config.pxi для Cython-збірки
└── src/
    └── file_paths.xml     # (використовувався для FileProvider; наразі не потрібен)
```

## Збірка

Потрібні: Python 3, [Buildozer](https://buildozer.readthedocs.io),
Android SDK/NDK (buildozer завантажить сам за потреби), JDK 17.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install buildozer cython

buildozer -v android debug
```

Готовий APK з'явиться в `bin/`.

### Нюанси збірки

Проєкт фіксує `python-for-android` на версії `v2024.01.21`
(`p4a.branch` у `buildozer.spec`) — новіші версії на момент розробки
мали нестабільну підтримку рецепту `pyjnius`. Через це знадобились
два локальні перевизначення рецептів (`local_recipes/`):

- **`pyjnius`** — рецепт цієї версії `p4a` іноді не генерує
  `jnius/config.pxi` перед Cython-компіляцією; перевизначення пише
  цей файл напряму.
- **`opencv`** — для коректної роботи `cv2.dnn` з ONNX-експортом
  YOLOv8 потрібна версія OpenCV новіша за дефолтну для цього рецепту
  (4.5.1); перевизначення адаптує патч збірки Python-біндингів під
  OpenCV 4.9.0.

**Шлях до проєкту не повинен містити кириличних символів** — деякі
інструменти збірки (зокрема `javac`, що викликається через `sh`)
некоректно обробляють такі шляхи.

## Подяки

- Датасет: [huyennguyen-wanak / skin-detection-pfmbg](https://universe.roboflow.com/huyennguyen-wanak/skin-detection-pfmbg) (Roboflow Universe, CC BY 4.0)
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
- [Kivy](https://kivy.org) / [KivyMD](https://kivymd.readthedocs.io) / [python-for-android](https://github.com/kivy/python-for-android)
