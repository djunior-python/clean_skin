"""
detector.py

Обгортка над OpenCV DNN для inference експортованої YOLOv8 ONNX моделі
детекції проблемних ділянок шкіри обличчя.

Перевірено в Colab: координати та впевненість збігаються з ultralytics.predict()
на тому самому зображенні (conf=0.15, imgsz=640).
"""

import os
import cv2
import numpy as np


# Порядок класів МАЄ точно відповідати data.yaml моделі (11 класів,
# після об'єднання cyst -> nodule і виправлення спліту).
CLASS_NAMES = [
    "Dark Circle",
    "Melasma",
    "PIH",
    "blackhead",
    "freckles",
    "nodule",
    "papule",
    "pustule",
    "skin-pore",
    "whitehead",
    "wrinkle",
]

# conf=0.15 обрано за результатами експериментів: нижче за дефолтні 0.25
# помітно піднімає recall для дрібних класів (blackhead, whitehead, pustule)
# без суттєвого падіння precision. Нижче 0.15 приросту вже немає (recall
# виходить на плато) — див. історію тестів conf=0.25/0.15/0.1/0.05.
DEFAULT_CONF_THRESHOLD = 0.15
DEFAULT_NMS_THRESHOLD = 0.5
INPUT_SIZE = 640


class SkinDetector:
    """
    Клас-обгортка над ONNX-моделлю. Ініціалізується один раз (завантаження
    мережі — відносно повільна операція), а метод detect() викликається
    для кожного нового зображення.
    """

    def __init__(self, model_path, conf_threshold=DEFAULT_CONF_THRESHOLD,
                 nms_threshold=DEFAULT_NMS_THRESHOLD, input_size=INPUT_SIZE,
                 class_names=None):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX-модель не знайдено: {model_path}")

        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.input_size = input_size
        self.class_names = class_names or CLASS_NAMES

    # ------------------------------------------------------------------
    # Препроцесинг
    # ------------------------------------------------------------------

    def _letterbox(self, image):
        """
        Приводить зображення до квадрату input_size x input_size
        з паддінгом (letterbox), як робить Ultralytics під час inference.
        Повертає padded-зображення і параметри, потрібні для того, щоб
        коректно перевести координати передбачень назад у систему
        координат оригінального зображення.
        """
        h, w = image.shape[:2]
        scale = self.input_size / max(h, w)
        new_w, new_h = int(round(w * scale)), int(round(h * scale))
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # 114 — сірий фон, той самий, що використовує Ultralytics для паддінгу
        padded = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        pad_x = (self.input_size - new_w) // 2
        pad_y = (self.input_size - new_h) // 2
        padded[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized

        return padded, scale, pad_x, pad_y

    # ------------------------------------------------------------------
    # Постпроцесинг
    # ------------------------------------------------------------------

    def _postprocess(self, output, scale, pad_x, pad_y, orig_w, orig_h):
        """
        Парсить сирий вихід форми (1, 4+nc, 8400) у список детекцій,
        застосовуючи поріг впевненості та NMS.
        """
        output = output[0]   # (4+nc, 8400)
        output = output.T    # (8400, 4+nc)

        boxes = []
        confidences = []
        class_ids = []

        for row in output:
            cx, cy, w, h = row[:4]
            class_scores = row[4:]
            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])

            if confidence < self.conf_threshold:
                continue

            # letterbox-координати -> координати оригінального зображення
            x = (cx - w / 2 - pad_x) / scale
            y = (cy - h / 2 - pad_y) / scale
            box_w = w / scale
            box_h = h / scale

            # відсікаємо бокси, що виходять за межі зображення
            x = max(0.0, x)
            y = max(0.0, y)
            box_w = min(box_w, orig_w - x)
            box_h = min(box_h, orig_h - y)

            boxes.append([int(x), int(y), int(box_w), int(box_h)])
            confidences.append(confidence)
            class_ids.append(class_id)

        detections = []
        if boxes:
            indices = cv2.dnn.NMSBoxes(
                boxes, confidences, self.conf_threshold, self.nms_threshold
            )
            if len(indices) > 0:
                for i in np.array(indices).flatten():
                    x, y, w, h = boxes[i]
                    detections.append({
                        "class": self.class_names[class_ids[i]],
                        "class_id": class_ids[i],
                        "confidence": confidences[i],
                        "bbox": [x, y, x + w, y + h],  # x1, y1, x2, y2
                    })

        return detections

    # ------------------------------------------------------------------
    # Публічне API
    # ------------------------------------------------------------------

    def detect(self, image):
        """
        image: numpy-масив BGR (як повертає cv2.imread), тобто те, з чим
        і працюватиме камера/галерея в Kivy-застосунку.

        Повертає список словників:
            {"class": str, "class_id": int, "confidence": float,
             "bbox": [x1, y1, x2, y2]}
        """
        orig_h, orig_w = image.shape[:2]
        padded, scale, pad_x, pad_y = self._letterbox(image)

        blob = cv2.dnn.blobFromImage(
            padded, scalefactor=1 / 255.0,
            size=(self.input_size, self.input_size),
            swapRB=True, crop=False,
        )
        self.net.setInput(blob)
        output = self.net.forward()

        return self._postprocess(output, scale, pad_x, pad_y, orig_w, orig_h)

    def detect_from_path(self, image_path):
        """Зручна обгортка: приймає шлях до файлу замість масиву."""
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Не вдалось прочитати зображення: {image_path}")
        return self.detect(image)

    @staticmethod
    def draw_detections(image, detections, box_color=(0, 255, 0), thickness=2):
        """Малює bbox і підписи прямо на переданому зображенні (мутує його)."""
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            label = f'{det["class"]} {det["confidence"]:.2f}'
            cv2.rectangle(image, (x1, y1), (x2, y2), box_color, thickness)
            cv2.putText(
                image, label, (x1, max(y1 - 5, 0)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, thickness,
            )
        return image


# ----------------------------------------------------------------------
# Швидка ручна перевірка: python detector.py path/to/model.onnx path/to/image.jpg
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Використання: python detector.py <model.onnx> <image.jpg>")
        sys.exit(1)

    model_path, image_path = sys.argv[1], sys.argv[2]

    detector = SkinDetector(model_path)
    detections = detector.detect_from_path(image_path)

    print(f"Знайдено {len(detections)} об'єктів:")
    for d in detections:
        print(f'  {d["class"]}: {d["confidence"]:.3f}, bbox={d["bbox"]}')

    image = cv2.imread(image_path)
    SkinDetector.draw_detections(image, detections)
    out_path = "detection_result.jpg"
    cv2.imwrite(out_path, image)
    print(f"Результат збережено у {out_path}")
