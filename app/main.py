import random

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label


class TTSApp(App):
    def _configure_wrapping_label(self, label, min_height=80):
        label.halign = "left"
        label.valign = "middle"
        label.size_hint_y = None
        label.height = min_height
        label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)),
            texture_size=lambda instance, value: setattr(
                instance, "height", max(min_height, value[1] + 20)
            ),
        )
        return label

    def build(self):
        self.tts = None
        self.tts_ready = False
        self.is_android = False
        self._TextToSpeech = None
        self._Locale = None
        self._Bundle = None
        self._HashMap = None
        self._JavaString = None
        self._tts_listener = None

        root = BoxLayout(orientation="vertical", padding=20, spacing=12)

        self.status = self._configure_wrapping_label(
            Label(text="Нажми кнопку, чтобы озвучить случайный текст")
        )
        speak_btn = Button(text="Сказать фразу", size_hint=(1, 0.3))
        speak_btn.bind(on_press=self.speak_random)

        root.add_widget(self.status)
        root.add_widget(speak_btn)

        self.init_tts()
        return root

    def init_tts(self):
        try:
            from jnius import PythonJavaClass, autoclass, java_method

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Locale = autoclass("java.util.Locale")
            Bundle = autoclass("android.os.Bundle")
            HashMap = autoclass("java.util.HashMap")
            JavaString = autoclass("java.lang.String")
            TextToSpeech = autoclass("android.speech.tts.TextToSpeech")

            app = self

            class TTSInitListener(PythonJavaClass):
                __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
                __javacontext__ = "app"

                def __init__(self):
                    super().__init__()

                @java_method("(I)V")
                def onInit(self, status):
                    Clock.schedule_once(lambda dt: app._on_tts_init(status), 0)

            self.is_android = True
            self._TextToSpeech = TextToSpeech
            self._Locale = Locale
            self._Bundle = Bundle
            self._HashMap = HashMap
            self._JavaString = JavaString
            self._tts_listener = TTSInitListener()
            self.tts = TextToSpeech(PythonActivity.mActivity, self._tts_listener)
            self.status.text = "Инициализирую Android TTS..."
        except Exception as e:
            self.status.text = f"Android TTS недоступен: {e}"

    def _on_tts_init(self, status):
        if self.tts is None or self._TextToSpeech is None:
            self.status.text = "TTS не создался"
            return

        if status != self._TextToSpeech.SUCCESS:
            self.status.text = f"Ошибка инициализации TTS: {status}"
            return

        try:
            language_status = self.tts.setLanguage(self._Locale.getDefault())
            if language_status == self._TextToSpeech.LANG_MISSING_DATA:
                self.status.text = "Для системного языка нет голосовых данных TTS"
                return
            if language_status == self._TextToSpeech.LANG_NOT_SUPPORTED:
                self.status.text = "Системный язык не поддерживается TTS"
                return

            self.tts_ready = True
            self.status.text = "TTS инициализирован. Нажми кнопку"
        except Exception as e:
            self.status.text = f"Ошибка настройки языка TTS: {e}"

    def speak_random(self, *_):
        phrases = [
            "Привет, это тест озвучки на Android",
            "Сегодня хороший день для экспериментов",
            "Умные очки почти готовы",
            "Проверка синтеза речи выполнена",
            "Случайная фраза успешно выбрана",
        ]
        text = random.choice(phrases)

        if not self.is_android or self.tts is None:
            self.status.text = f"(Не Android) Выбрано: {text}"
            return

        if not self.tts_ready:
            self.status.text = "TTS еще не готов, подожди секунду и нажми снова"
            return

        try:
            result = None
            java_text = self._JavaString(text)
            try:
                params = self._Bundle()
                result = self.tts.speak(
                    java_text,
                    self._TextToSpeech.QUEUE_FLUSH,
                    params,
                    "utterance_id_1",
                )
            except TypeError:
                params = self._HashMap()
                result = self.tts.speak(
                    java_text,
                    self._TextToSpeech.QUEUE_FLUSH,
                    params,
                )

            if result == self._TextToSpeech.ERROR:
                self.status.text = "TTS вернул ошибку при озвучке"
                return

            self.status.text = f"Озвучено: {text}"
        except Exception as e:
            self.status.text = f"Ошибка озвучки: {e}"

    def on_stop(self):
        if self.tts is not None:
            try:
                self.tts.stop()
                self.tts.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    TTSApp().run()
