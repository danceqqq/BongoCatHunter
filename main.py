import sys
import time
import numpy as np
import cv2
import psutil
import win32gui
import win32process
import win32api
import win32con
from PIL import Image
import mss
import colorama
from colorama import Fore

colorama.init()

# Конфигурация
TARGET_COLORS = [(223, 195, 112), (213, 189, 115), (225, 200, 99)]  # Цвета пикселей
TEMPLATE_PATH = 'img/chest.jpg'  # Путь к шаблону изображения
TEMPLATE_THRESHOLD = 0.8  # Порог совпадения шаблона (0-1)
CLICK_OFFSET = (0, 0)  # Смещение клика относительно найденной позиции
CLICK_COUNT = 3  # Количество кликов
CLICK_DELAY = 0.1  # Задержка между кликами (сек)
INITIAL_CHECK_INTERVAL = 60  # Начальный интервал проверки (сек)
EXTENDED_CHECK_INTERVAL = 1860  # Расширенный интервал после клика (31 мин)

# Загрузка шаблона
template = cv2.imread(TEMPLATE_PATH, 0)
if template is None:
    raise FileNotFoundError(f"Шаблон {TEMPLATE_PATH} не найден")


def find_bongocat_process():
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] == 'BongoCat.exe':
            return proc.info['pid']
    return None


def get_hwnd_by_pid(pid):
    def callback(hwnd, hwnds):
        if win32gui.IsWindowVisible(hwnd):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid:
                hwnds.append(hwnd)

    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
    return hwnds[0] if hwnds else None


def capture_window(hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    with mss.mss() as sct:
        monitor = {
            'left': rect[0],
            'top': rect[1],
            'width': rect[2] - rect[0],
            'height': rect[3] - rect[1]
        }
        screenshot = sct.grab(monitor)
        img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
        return np.array(img), rect


def find_template(image):
    img_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= TEMPLATE_THRESHOLD)
    points = list(zip(*loc[::-1]))
    return points


def multi_click(x, y, hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    absolute_x = rect[0] + x + CLICK_OFFSET[0]
    absolute_y = rect[1] + y + CLICK_OFFSET[1]

    # Сохраняем текущую позицию курсора
    original_pos = win32api.GetCursorPos()

    for _ in range(CLICK_COUNT):
        # Эмулируем клик без перемещения курсора
        win32api.SetCursorPos((absolute_x, absolute_y))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.01)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(CLICK_DELAY)

    # Возвращаем курсор в исходную позицию
    win32api.SetCursorPos(original_pos)
    print(f"{Fore.YELLOW}Выполнено {CLICK_COUNT} кликов в ({absolute_x}, {absolute_y}){Fore.RESET}")


def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def main():
    print("Начинаем мониторинг... Нажмите Ctrl+C для выхода")
    first_click = True
    check_interval = INITIAL_CHECK_INTERVAL

    try:
        while True:
            pid = find_bongocat_process()

            if not pid:
                print(f"\r{Fore.RED}Окно не найдено. Проверка каждые 10 сек...{Fore.RESET}", end="")
                time.sleep(10)
                continue

            hwnd = get_hwnd_by_pid(pid)
            if not hwnd:
                print(f"\r{Fore.RED}Не найдено окно процесса{Fore.RESET}")
                time.sleep(10)
                continue

            print(f"\n{Fore.GREEN}=== Окно BongoCat найдено! ==={Fore.RESET}")

            while True:
                # Логика таймера с динамическим интервалом
                total_time = check_interval
                start_time = time.time()

                while True:
                    elapsed = int(time.time() - start_time)
                    remaining = max(total_time - elapsed, 0)

                    # Форматируем вывод времени
                    if check_interval == INITIAL_CHECK_INTERVAL:
                        timer_str = f"Следующая проверка через: {remaining:2d} сек"
                    else:
                        timer_str = f"Следующая проверка через: {format_time(remaining)}"

                    print(f"\r{timer_str}{' ' * 10}", end="", flush=True)

                    if remaining <= 0:
                        break
                    time.sleep(0.5)

                # Проверка существования процесса
                if not psutil.pid_exists(pid):
                    print(f"\n{Fore.RED}Процесс завершился{Fore.RESET}")
                    check_interval = INITIAL_CHECK_INTERVAL  # Сброс интервала
                    break

                # Захватываем окно
                image, rect = capture_window(hwnd)
                found = False

                # Поиск пикселей
                for y in range(image.shape[0]):
                    for x in range(image.shape[1]):
                        pixel = tuple(image[y, x])
                        if pixel in TARGET_COLORS:
                            print(f"\n{Fore.CYAN}Найден целевой пиксель: {pixel} на ({x}, {y}){Fore.RESET}")
                            multi_click(x, y, hwnd)
                            found = True
                            break
                    if found:
                        break

                # Поиск изображения
                if not found:
                    points = find_template(image)
                    if points:
                        print(f"\n{Fore.MAGENTA}Найден шаблон! Количество совпадений: {len(points)}{Fore.RESET}")
                        for pt in points:
                            multi_click(pt[0], pt[1], hwnd)
                            found = True

                # Изменение интервала после первого клика
                if found and first_click:
                    check_interval = EXTENDED_CHECK_INTERVAL
                    first_click = False
                    print(f"\n{Fore.BLUE}Интервал проверки изменен на 31 минуту{Fore.RESET}")

                if not found:
                    print(f"\r{Fore.WHITE}Ничего не найдено{' ' * 20}{Fore.RESET}", end="")

    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем")
        sys.exit(0)


if __name__ == '__main__':
    main()