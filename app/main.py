import random

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label


class TTSApp(App):
    def build(self):
        self.tts = None
        self.is_android = False

        root = BoxLayout(orientation="vertical", padding=20, spacing=12)

        self.status = Label(text="Нажми кнопку, чтобы озвучить случайный текст")
        speak_btn = Button(text="Сказать фразу", size_hint=(1, 0.3))
        speak_btn.bind(on_press=self.speak_random)

        root.add_widget(self.status)
        root.add_widget(speak_btn)

        self.init_tts()
        return root

    def init_tts(self):
        try:
            from jnius import autoclass, cast
            from android import mActivity

            Locale = autoclass("java.util.Locale")
            TextToSpeech = autoclass("android.speech.tts.TextToSpeech")

            self.is_android = True
            self._TextToSpeech = TextToSpeech
            self._Locale = Locale
            self._activity = cast("android.app.Activity", mActivity)
            self.tts = TextToSpeech(self._activity, None)

            # Пытаемся выставить язык системы (если доступен)
            self.tts.setLanguage(Locale.getDefault())
            self.status.text = "TTS инициализирован. Нажми кнопку"
        except Exception as e:
            self.status.text = f"Android TTS недоступен: {e}"

    def speak_random(self, *_):
        phrases = [
            "Привет, это тест озвучки на Android",
            "Сегодня хороший день для экспериментов",
            "Умные очки почти готовы",
            "Проверка синтеза речи выполнена",
            "Случайная фраза успешно выбрана",
        ]
        text = random.choice(phrases)

        if self.is_android and self.tts is not None:
            try:
                self.tts.speak(text, self._TextToSpeech.QUEUE_FLUSH, None, "utterance_id_1")
                self.status.text = f"Озвучено: {text}"
            except Exception as e:
                self.status.text = f"Ошибка озвучки: {e}"
        else:
            self.status.text = f"(Не Android) Выбрано: {text}"

    def on_stop(self):
        if self.tts is not None:
            try:
                self.tts.stop()
                self.tts.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    TTSApp().run()
