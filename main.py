"""
main.py (версія на KivyMD)

Той самий потік, що й раніше (фото/галерея -> SkinDetector -> показ
результату), але UI переписаний на компоненти KivyMD 1.2.0 для
сучаснішого вигляду (заокруглені кнопки, картка із тінню, індикатор
завантаження) - орієнтир: наданий макет.

Логіка детекції (detector.py) не змінювалась і використовується так
само, як у попередній версії.
"""

import os
import threading
import traceback

import cv2

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDFillRoundFlatIconButton
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.scrollview import MDScrollView

from kivy.uix.image import Image as KivyImage
from kivy.clock import mainthread

from detector import SkinDetector

try:
    from android.permissions import request_permissions, Permission
    ON_ANDROID = True
except ImportError:
    ON_ANDROID = False

try:
    from plyer import camera, filechooser
except ImportError:
    camera = None
    filechooser = None


MODEL_FILENAME = "best.onnx"

# Код запиту для startActivityForResult (довільне число, головне - єдиний
# для нашої камери) і значення android.app.Activity.RESULT_OK.
CAMERA_REQUEST_CODE = 0x123
ANDROID_RESULT_OK = -1
PLACEHOLDER_TEXT = "Зробіть фото або оберіть зображення для аналізу"


def get_model_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), MODEL_FILENAME)


class RootScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.detector = None
        self.detector_error = None

        root_layout = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="12dp",
        )

        # ---- Картка із зображенням/плейсхолдером ----
        self.image_card = MDCard(
            orientation="vertical",
            padding="4dp",
            radius=[24, 24, 24, 24],
            elevation=2,
            size_hint=(1, 0.62),
        )
        self.image_widget = KivyImage(allow_stretch=True, keep_ratio=True)
        self.image_card.add_widget(self.image_widget)
        root_layout.add_widget(self.image_card)

        # ---- Статус-текст під карткою ----
        self.status_label = MDLabel(
            text=PLACEHOLDER_TEXT,
            halign="center",
            size_hint=(1, None),
            height="28dp",
        )
        root_layout.add_widget(self.status_label)

        # ---- Індикатор завантаження (видимий лише під час аналізу) ----
        self.progress = MDProgressBar(
            type="indeterminate",
            size_hint=(1, None),
            height="4dp",
            opacity=0,
        )
        root_layout.add_widget(self.progress)

        # ---- Список знайдених класів (прокручуваний, компактний) ----
        results_scroll = MDScrollView(size_hint=(1, 0.16))
        self.results_label = MDLabel(
            text="",
            halign="left",
            valign="top",
            size_hint=(1, None),
        )
        self.results_label.bind(
            texture_size=lambda inst, size: setattr(inst, "height", size[1])
        )
        self.results_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None))
        )
        results_scroll.add_widget(self.results_label)
        root_layout.add_widget(results_scroll)

        # ---- Дві заокруглені кнопки внизу (як на макеті) ----
        buttons_box = MDBoxLayout(
            orientation="vertical",
            spacing="10dp",
            size_hint=(1, None),
            height="120dp",
        )

        self.camera_button = MDFillRoundFlatIconButton(
            text="Зробити фото",
            icon="camera",
            size_hint=(1, None),
            height="52dp",
            pos_hint={"center_x": 0.5},
        )
        self.camera_button.bind(on_release=self.on_camera_pressed)
        buttons_box.add_widget(self.camera_button)

        self.gallery_button = MDFillRoundFlatIconButton(
            text="Обрати з галереї",
            icon="image-multiple",
            size_hint=(1, None),
            height="52dp",
            pos_hint={"center_x": 0.5},
        )
        self.gallery_button.bind(on_release=self.on_gallery_pressed)
        buttons_box.add_widget(self.gallery_button)

        root_layout.add_widget(buttons_box)

        # ---- Блок діагностики (traceback) - малий, знизу, лишаємо для
        #      тестування; прибрати легко, коли все стабільно ----
        error_scroll = MDScrollView(size_hint=(1, 0.14))
        self.error_label = MDLabel(
            text="",
            halign="left",
            valign="top",
            theme_text_color="Custom",
            text_color=(0.8, 0.2, 0.2, 1),
            font_style="Caption",
            size_hint=(1, None),
        )
        self.error_label.bind(
            texture_size=lambda inst, size: setattr(inst, "height", size[1])
        )
        self.error_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None))
        )
        error_scroll.add_widget(self.error_label)
        root_layout.add_widget(error_scroll)

        self.add_widget(root_layout)

        self._load_detector()

    # ------------------------------------------------------------------
    def _load_detector(self):
        model_path = get_model_path()
        try:
            self.detector = SkinDetector(model_path)
        except Exception:
            tb_text = traceback.format_exc()
            self.detector_error = tb_text
            self.status_label.text = "Помилка завантаження моделі - деталі нижче"
            self.error_label.text = tb_text
            print(tb_text)

    # ------------------------------------------------------------------
    def on_camera_pressed(self, instance):
        photo_path = os.path.join(self._get_temp_dir(), "camera_photo.jpg")

        if ON_ANDROID:
            self._take_photo_android(photo_path)
            return

        # Десктоп / тестування: штатний plyer
        if camera is None:
            self.status_label.text = "Камера недоступна на цій платформі"
            return

        try:
            camera.take_picture(filename=photo_path, on_complete=self._on_photo_taken)
        except Exception as e:
            self.status_label.text = f"Не вдалось відкрити камеру: {e}"
            traceback.print_exc()

    def _take_photo_android(self, photo_path):
        """
        Запускає системну камеру через intent. Замість того, щоб самим
        оголошувати FileProvider (маніфест, xml-ресурс, окремий рецепт),
        просимо систему створити запис у Галереї (MediaStore) і віддати
        нам готовий content://-URI - це вбудований системний провайдер,
        тож FileUriExposedException тут в принципі не виникає: ми ніколи
        не передаємо камері сирий file://-шлях.

        Побічний ефект: знімок буде видно в Галереї користувача (як і в
        більшості звичайних фотододатків). Якщо це небажано, можна
        видалити запис із MediaStore одразу після обробки - див.
        коментар у кінці _on_camera_result.

        Java-класи імпортуємо тут, а не на початку файлу: якщо чогось
        бракує, помилка з'явиться в панелі діагностики, а застосунок не
        впаде під час запуску.
        """
        try:
            from android import activity as android_activity
            from jnius import autoclass, cast

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            MediaStore = autoclass("android.provider.MediaStore")
            MediaStoreImagesMedia = autoclass("android.provider.MediaStore$Images$Media")
            ContentValues = autoclass("android.content.ContentValues")

            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()

            values = ContentValues()
            # Буквальні назви колонок замість успадкованих статичних
            # полів (MediaStoreImagesMedia.DISPLAY_NAME/MIME_TYPE) - ці
            # поля pyjnius іноді не резолвить коректно через autoclass,
            # бо вони успадковані від MediaStore.MediaColumns, а не
            # оголошені прямо в MediaStore.Images.Media. Самі рядки
            # ("_display_name", "mime_type") - стабільні системні назви
            # колонок, однакові на всіх версіях Android.
            values.put("_display_name", "skin_detector_photo.jpg")
            values.put("mime_type", "image/jpeg")
            # Android 10+ (Scoped Storage): MediaProvider у багатьох
            # випадках вимагає relative_path, інакше insert() падає з
            # "IllegalArgumentException: Invalid column null" - система
            # не знає, у яку публічну директорію класти файл.
            values.put("relative_path", "Pictures/SkinDetector")

            uri = resolver.insert(MediaStoreImagesMedia.EXTERNAL_CONTENT_URI, values)
            if uri is None:
                self._set_status_threadsafe("Не вдалось створити файл для фото")
                return

            intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            intent.putExtra(MediaStore.EXTRA_OUTPUT, cast("android.os.Parcelable", uri))
            intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)

            self._pending_photo_uri = uri
            self._pending_photo_path = photo_path
            android_activity.unbind(on_activity_result=self._on_camera_result)
            android_activity.bind(on_activity_result=self._on_camera_result)
            activity.startActivityForResult(intent, CAMERA_REQUEST_CODE)

        except Exception:
            tb_text = traceback.format_exc()
            self._set_status_threadsafe("Не вдалось відкрити камеру - деталі нижче")
            self._set_error_threadsafe(tb_text)
            print(tb_text)

    def _on_camera_result(self, request_code, result_code, intent):
        if request_code != CAMERA_REQUEST_CODE:
            return

        from android import activity as android_activity
        android_activity.unbind(on_activity_result=self._on_camera_result)

        if result_code != ANDROID_RESULT_OK:
            self._set_status_threadsafe("Знімок скасовано")
            return

        uri = getattr(self, "_pending_photo_uri", None)
        local_path = getattr(self, "_pending_photo_path", None)
        if uri is None or local_path is None:
            self._set_status_threadsafe("Фото не отримано")
            return

        try:
            self._copy_content_uri_to_file(uri, local_path)
        except Exception:
            tb_text = traceback.format_exc()
            self._set_status_threadsafe("Не вдалось прочитати фото - деталі нижче")
            self._set_error_threadsafe(tb_text)
            print(tb_text)
            return

        # Інференс - в окремому потоці, щоб не блокувати потік Android UI,
        # з якого приходить цей колбек
        threading.Thread(
            target=self._process_image, args=(local_path,), daemon=True
        ).start()

        # Якщо НЕ хочеш, щоб знімки лишались у Галереї користувача,
        # розкоментуй ці два рядки - видалить запис із MediaStore одразу
        # після того, як ми скопіювали дані собі:
        # from android.runnable import run_on_ui_thread
        # ...resolver.delete(uri, None, None) (з правильного потоку)

    def _copy_content_uri_to_file(self, uri, dest_path):
        """
        content://-URI не є шляхом на файловій системі - cv2.imread() з
        ним не працює. Читаємо байти через ContentResolver і зберігаємо
        у звичайний локальний файл, який далі йде в детектор як завжди.

        Стандартний pyjnius-ідіом для повного вичитування InputStream:
        передаємо Python bytearray у input_stream.read(buf) - pyjnius
        сам конвертує його в Java byte[], read() повертає кількість
        реально прочитаних байтів (або -1 на кінці потоку).
        """
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        ByteArrayOutputStream = autoclass("java.io.ByteArrayOutputStream")

        activity = PythonActivity.mActivity
        resolver = activity.getContentResolver()

        input_stream = resolver.openInputStream(uri)
        baos = ByteArrayOutputStream()
        buf = bytearray(8192)

        try:
            while True:
                n = input_stream.read(buf)
                if n == -1:
                    break
                baos.write(buf, 0, n)
        finally:
            input_stream.close()

        data = bytes(baos.toByteArray())
        with open(dest_path, "wb") as out_file:
            out_file.write(data)

    def _on_photo_taken(self, photo_path):
        if not photo_path or not os.path.exists(photo_path):
            self._set_status_threadsafe("Фото не отримано")
            return
        self._process_image(photo_path)

    # ------------------------------------------------------------------
    def on_gallery_pressed(self, instance):
        if filechooser is None:
            self.status_label.text = "Вибір файлів недоступний на цій платформі"
            return

        try:
            filechooser.open_file(
                on_selection=self._on_gallery_selected,
                filters=["*.jpg", "*.jpeg", "*.png"],
            )
        except Exception as e:
            self.status_label.text = f"Не вдалось відкрити галерею: {e}"
            traceback.print_exc()

    def _on_gallery_selected(self, selection):
        if not selection:
            return
        self._process_image(selection[0])

    # ------------------------------------------------------------------
    def _process_image(self, image_path):
        if self.detector is None:
            self._set_status_threadsafe(f"Модель не завантажена: {self.detector_error}")
            return

        self._show_progress_threadsafe(True)
        self._set_status_threadsafe("Аналіз...")
        self._set_error_threadsafe("")

        try:
            image = cv2.imread(image_path)
            if image is None:
                self._set_status_threadsafe(f"Не вдалось прочитати файл: {image_path}")
                return

            detections = self.detector.detect(image)
            SkinDetector.draw_detections(image, detections)
            self._show_result(image, detections)

        except Exception:
            tb_text = traceback.format_exc()
            self._set_status_threadsafe("Помилка аналізу - деталі нижче")
            self._set_error_threadsafe(tb_text)
            print(tb_text)
        finally:
            self._show_progress_threadsafe(False)

    @mainthread
    def _set_status_threadsafe(self, text):
        self.status_label.text = text

    @mainthread
    def _set_error_threadsafe(self, text):
        self.error_label.text = text

    @mainthread
    def _show_progress_threadsafe(self, visible):
        self.progress.opacity = 1 if visible else 0

    @mainthread
    def _show_result(self, bgr_image, detections):
        result_path = os.path.join(self._get_temp_dir(), "result.png")
        cv2.imwrite(result_path, bgr_image)

        self.image_widget.source = ""
        self.image_widget.source = result_path
        self.image_widget.reload()

        if detections:
            self.status_label.text = f"Знайдено {len(detections)} ділянок"
            lines = [f'- {d["class"]}: {d["confidence"]:.2f}' for d in detections]
            self.results_label.text = "\n".join(lines)
        else:
            self.status_label.text = "Проблемних ділянок не знайдено"
            self.results_label.text = ""

    # ------------------------------------------------------------------
    def _get_temp_dir(self):
        app = MDApp.get_running_app()
        temp_dir = app.user_data_dir
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir


class SkinDetectorApp(MDApp):
    def build(self):
        if ON_ANDROID:
            request_permissions([
                Permission.CAMERA,
                Permission.READ_MEDIA_IMAGES,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])

        self.title = "Skin Detector"
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Teal"

        return RootScreen()


if __name__ == "__main__":
    SkinDetectorApp().run()