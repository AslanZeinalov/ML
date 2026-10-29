#!/usr/bin/env python3
import re
import datetime
from collections import Counter, defaultdict
import os
import pytest
import requests
from bs4 import BeautifulSoup


class Links:
    """
    Analyzing data from links.csv
    """

    def __init__(self, path_to_the_file, path_to_movies):
        """
        Put here any fields that you think you will need.
        """
        if not os.path.exists(path_to_the_file):
            raise FileNotFoundError(f"Файл {path_to_the_file} не существует")

        self.path = path_to_the_file

        # 1. Проверяем наличие спарсенного файла imdb_data.csv
        self.parsed_file = os.path.join(os.path.dirname(self.path), 'imdb_data.csv')
        if not os.path.exists(self.parsed_file):
            print("Файл 'imdb_data.csv' не найден, запускаем срапинг...")
            self.scrape_imdb_data()
            print("Скрапинг завершен.")


        # 2. Читаем links.csv (для получения списка movieId)
        self.movie_ids = self._get_movie_ids()

        # 3. Загружаем названия фильмов из movies.csv
        self.moviespath = path_to_movies
        self.moviesdata = self._get_movies()

        # 4. Загружаем спарсенные данные в память
        self.imdb_cache = self._load_parsed_data()

    def _get_movie_ids(self):
        """Читаем только ID фильмов из links.csv"""
        ids = []
        with open(self.path, 'r', encoding='utf-8') as file:
            next(file)
            for i, line in enumerate(file):
                if i >= 1000:
                    break
                parts = line.strip().split(',')
                if len(parts) >= 1:
                    ids.append(parts[0])
        return ids

    def _get_movies(self):
        """
        Returns dict using movies.csv with pairs {movieId: title}
        Uses regex to handle titles with commas correctly.
        """
        data = {}
        if not os.path.exists(self.moviespath):
            raise FileNotFoundError(f"Файл {self.moviespath} не существует")

        with open(self.moviespath, 'r', encoding='utf-8') as file:
            next(file)  # Skip header
            for line in file:
                line = line.strip()
                # Используем regex для правильного разделения CSV с кавычками
                parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)

                # movies.csv: movieId,title,genres (минимум 2 колонки)
                if len(parts) >= 2:
                    movie_id = parts[0]
                    title = parts[1].strip('"')  # Убираем лишние кавычки
                    data[movie_id] = title
        return data

    def _load_parsed_data(self):
        """Читаем imdb_data.csv в словарь без библиотеки csv"""
        cache = {}
        with open(self.parsed_file, 'r', encoding='utf-8') as f:
            # Читаем заголовок, чтобы понять порядок колонок
            header_line = next(f).strip()
            headers = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', header_line)

            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)

                # Создаем словарь row, сопоставляя заголовки и значения
                row = {}
                for i, header in enumerate(headers):
                    if i < len(parts):
                        row[header] = parts[i]

                movieId = row.get('movieId')
                if movieId:
                    cache[movieId] = row
        return cache

    @staticmethod
    def _extract_value(value_str):
        """Превращает '$1,000,000' в число и '2h 15m' в минуты"""
        if not value_str:
            return None

        # Проверяем, похоже ли это на время (цифры + h или m)
        is_runtime = re.search(r'\d+\s*(h|m|min)', value_str)

        if is_runtime:
            hours = 0
            minutes = 0

            h_match = re.search(r'(\d+)\s*h', value_str)
            if h_match:
                hours = int(h_match.group(1))

            m_match = re.search(r'(\d+)\s*m', value_str)
            if m_match:
                minutes = int(m_match.group(1))

            # Если формат "81 min" (без h)
            if hours == 0 and minutes == 0:
                min_match = re.search(r'(\d+)\s*min', value_str)
                if min_match:
                    minutes = int(min_match.group(1))

            total = hours * 60 + minutes
            return total if total > 0 else None

        # Парсинг денег
        if '$' not in value_str:
            return None
        cleaned = re.sub(r'[^\d.]', '', value_str)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    def get_imdb(self, list_of_movies, list_of_fields):
        """
The method returns a list of lists [movieId, field1, field2, field3, ...] for the list of movies given as the argument (movieId).
        For example, [movieId, Director, Budget, Cumulative Worldwide Gross, Runtime].
        The values should be parsed from the IMDB webpages of the movies.
     Sort it by movieId descendingly.
        """
        imdb_info = []

        for movieId in list_of_movies:
            movieId_str = str(movieId)

            # Берем данные из загруженного кэша IMDb
            data_row = self.imdb_cache.get(movieId_str)

            row = [movieId]

            for field in list_of_fields:
                val = None

                # Если запрашивают Title, берем его из movies.csv (self.moviesdata)
                if field == 'Title':
                    val = self.moviesdata.get(movieId_str)
                    # Если в movies.csv нет, пробуем взять из IMDb как запасной вариант
                    if not val and data_row:
                        val = data_row.get(field)

                # Для остальных полей берем из IMDb кэша
                elif data_row:
                    val = data_row.get(field)

                # Если значение пустая строка, превращаем в None
                if val == '':
                    val = None
                row.append(val)

            imdb_info.append(row)

        # Сортировка по movieId убыванию (descendingly)
        imdb_info.sort(key=lambda x: int(x[0]), reverse=True)

        return imdb_info

    def top_directors(self, n):
        """
        The method returns a dict with top-n directors where the keys are directors and
        the values are numbers of movies created by them. Sort it by numbers descendingly.
        """
        movies = self.movie_ids
        data = self.get_imdb(movies, ['Director'])

        all_directors = []
        for row in data:
            directors_str = row[1]
            if directors_str:
                names = [name.strip() for name in directors_str.split(',')]
                all_directors.extend(names)

        return dict(Counter(all_directors).most_common(n))

    def most_expensive(self, n):
        """
        The method returns a dict with top-n movies where the keys are movie titles and
        the values are their budgets. Sort it by budgets descendingly.
        """
        movies = self.movie_ids
        # Запрашиваем Title, который теперь подтянется из movies.csv
        data = self.get_imdb(movies, ['Title', 'Budget'])

        result = {}
        for row in data:
            title = row[1]
            budget_str = row[2]
            val = Links._extract_value(budget_str)

            if title and val:
                result[title] = val

        sorted_res = sorted(result.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_res[:n])

    def most_profitable(self, n):
        """
        The method returns a dict with top-n movies where the keys are movie titles and
        the values are the difference between cumulative worldwide gross and budget.
     Sort it by the difference descendingly.
        """
        movies = self.movie_ids
        data = self.get_imdb(movies, ['Title', 'Budget', 'Cumulative Worldwide Gross'])

        result = {}
        for row in data:
            title = row[1]
            budget_val = Links._extract_value(row[2])
            gross_val = Links._extract_value(row[3])

            if title and budget_val and gross_val:
                profit = gross_val - budget_val
                result[title] = profit

        sorted_res = sorted(result.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_res[:n])

    def longest(self, n):
        """
        The method returns a dict with top-n movies where the keys are movie titles and
        the values are their runtime. If there are more than one version – choose any.
     Sort it by runtime descendingly.
        """
        movies = self.movie_ids
        data = self.get_imdb(movies, ['Title', 'Runtime'])

        result = {}
        for row in data:
            title = row[1]
            runtime_val = Links._extract_value(row[2])

            if title and runtime_val:
                result[title] = runtime_val

        sorted_res = sorted(result.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_res[:n])

    def top_cost_per_minute(self, n):
        """
        The method returns a dict with top-n movies where the keys are movie titles and
the values are the budgets divided by their runtime. The budgets can be in different currencies – do not pay attention to it.
     The values should be rounded to 2 decimals. Sort it by the division descendingly.
        """
        movies = self.movie_ids
        data = self.get_imdb(movies, ['Title', 'Runtime', 'Budget'])

        result = {}
        for row in data:
            title = row[1]
            runtime_val = Links._extract_value(row[2])
            budget_val = Links._extract_value(row[3])

            if title and runtime_val and budget_val and runtime_val > 0:
                cpm = budget_val / runtime_val
                result[title] = round(cpm, 2)

        sorted_res = sorted(result.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_res[:n])

    def roi_by_director(self, n):
        """
        Бонусная часть. Возвращает топ-n режисеров с наибольшим средним ROI
        """
        movies = self.movie_ids
        data = self.get_imdb(movies, ['Director', 'Budget', 'Cumulative Worldwide Gross'])

        roi_by_director = defaultdict(list)

        for row in data:
            director_str = row[1]
            budget_val = Links._extract_value(row[2])
            gross_val = Links._extract_value(row[3])

            if director_str and budget_val and gross_val and budget_val > 0:
                roi = (gross_val - budget_val) / budget_val
                for director in director_str.split(','):
                    director = director.strip()
                    roi_by_director[director].append(roi)

        avg_roi = {director: round(sum(rois)/len(rois), 2) for director, rois in roi_by_director.items()}
        return dict(sorted(avg_roi.items(), key=lambda x: x[1], reverse=True)[:n])

    def scrape_imdb_data(self):
        def get_imdb_field(soup, field_name):
            try:
                if field_name == 'Director':
                    item = soup.find('li', {'data-testid': 'title-pc-principal-credit'})
                    if item:
                        links = item.find_all('a', href=re.compile(r'/name/'))
                        names = [l.text.strip() for l in links]
                        return ', '.join(names) if names else None
                    label = soup.find('span', string=re.compile(r'^Director'))
                    if label and label.parent:
                        links = label.parent.find_all('a', href=re.compile(r'/name/'))
                        names = [l.text.strip() for l in links]
                        return ', '.join(names) if names else None

                elif field_name == 'Budget':
                    item = soup.find('li', {'data-testid': 'title-boxoffice-budget'})
                    if item:
                        val = item.find('span', class_='ipc-metadata-list-item__list-content-item')
                        return val.text.strip() if val else None
                    label = soup.find('span', string='Budget')
                    if label and label.parent:
                        return label.parent.get_text(strip=True).replace('Budget', '')

                elif field_name == 'Cumulative Worldwide Gross':
                    item = soup.find('li', {'data-testid': 'title-boxoffice-cumulativeworldwidegross'})
                    if item:
                        val = item.find('span', class_='ipc-metadata-list-item__list-content-item')
                        return val.text.strip() if val else None

                elif field_name == 'Runtime':
                    # Приоритет: заголовок
                    header_list = soup.find('ul', {'data-testid': 'hero-title-block__metadata'})
                    if header_list:
                        for li in header_list.find_all('li'):
                            text = li.get_text(strip=True)
                            if 'h' in text or 'm' in text:
                                return text
                    item = soup.find('li', {'data-testid': 'title-techspec_runtime'})
                    if item:
                        div = item.find('div', class_='ipc-metadata-list-item__content-container')
                        return div.text.strip() if div else None
                    div = soup.find('div', {'data-testid': 'title-runtime'})
                    if div: return div.text.strip()

                elif field_name == 'Title':
                    h1 = soup.find('h1')
                    if h1: return h1.text.strip()
            except:
                pass
            return None

        # --- ФУНКЦИЯ ЭКРАНИРУЕТ ПОЛЕ ЕСЛИ В НЕМ ЕСТЬ ЗАПЯТЫЕ, КАВЫЧКИ ИЛИ СИМВОЛ НОВОЙ СТРОКИ
        #  АЛЬТЕРНАТИВА БИБЛИОТЕКЕ CSV Т.К. ЕЕ НЕТ В РАЗРЕШЕННЫХ ---

        def escape_csv_field(field):
            if field is None:
                return ""
            field = str(field)
            needs_quoting = ',' in field or '"' in field or '\n' in field
            if needs_quoting:
                field = '"'+field.replace('"', '""')+'"'
            return field

        # --- Замена time.sleep() так как этой бибилиотеки нет в разрешенных ---

        def sleep(seconds):
            start = datetime.datetime.now()
            while True:
                now = datetime.datetime.now()
                if (now - start).total_seconds() >= seconds:
                    break

        # --- ОСНОВНОЙ СКРИПТ ---

        INPUT_FILE = '../datasets/links.csv'
        OUTPUT_FILE = 'imdb_data.csv'

        # Заголовки для CSV
        COLUMNS = ['movieId', 'Director', 'Budget', 'Cumulative Worldwide Gross', 'Runtime', 'Title']

        # Настройка сессии
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=1.0'
        })

        # 1. Читаем links.csv
        links_map = {} # movieId -> imdbId
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            next(f)
            for i, line in enumerate(f):
                if i >= 1000: break
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    links_map[parts[0]] = parts[1]

        # 2. Проверяем, что уже скачано (чтобы можно было докачать при сбое)
        scraped_ids = set()
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                next(f)
                for line in f:
                    line = line.strip()
                    if not line: continue
                    movieId = line.split(',', 1)[0]
                    scraped_ids.add(movieId)
        else:
            # Создаем файл с заголовками
            with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
                f.write(','.join(COLUMNS) + '\n')

        print(f"Всего фильмов: {len(links_map)}. Уже скачано: {len(scraped_ids)}")

        count = 0
        for movieId, imdbId in links_map.items():
            if movieId in scraped_ids:
                continue

            url = f"https://www.imdb.com/title/tt{imdbId.zfill(7)}/"
            print(f"[{count+1}] Parsing {movieId} ({url})...", end=" ")

            row_data = [movieId]
            try:
                resp = session.get(url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    row_data.append(get_imdb_field(soup, 'Director'))
                    row_data.append(get_imdb_field(soup, 'Budget'))
                    row_data.append(get_imdb_field(soup, 'Cumulative Worldwide Gross'))
                    row_data.append(get_imdb_field(soup, 'Runtime'))
                    row_data.append(get_imdb_field(soup, 'Title'))
                    print("OK")
                else:
                    print(f"Error {resp.status_code}")
                    row_data.extend([None]*5)
            except Exception as e:
                print(f"Exception: {e}")
                row_data.extend([None]*5)

            row_str = ','.join([escape_csv_field(item) if item is not None else '' for item in row_data])
            with open(OUTPUT_FILE, 'a', encoding='utf-8', newline='') as f:
                f.write(row_str + '\n')

            count += 1

            sleep(0.5)

        print("Готово! Файл imdb_data.csv создан.")


class Movies:
    """
    Analyzing data from movies.csv
    """

    def __init__(self, path_to_the_file):
        if not os.path.exists(path_to_the_file):
            raise FileNotFoundError(f"Файл {path_to_the_file} не существует")
        self.path = path_to_the_file

    def _get_data(self):
        """
        Вспомогательный метод (поэтому начинается с _),
        который читает файл и правильно его парсит.
        """
        data = []
        with open(self.path, 'r', encoding='utf-8') as file:
            next(file)  # Пропуск заголовка

            for i, line in enumerate(file):
                if i >= 1000:  # Ограничение задания
                    break

                line = line.strip()
                # Regex для правильного разделения CSV с кавычками
                # Делим по запятой, только если за ней следует четное количество кавычек
                parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)

                # parts[0] = id, parts[1] = title, parts[2] = genres
                if len(parts) >= 3:
                    data.append(parts)
        return data
    
    def top_genres_by_decade(self):
        """
        Возвращает словарь, где ключи — десятилетия (например, '1990s'),
        а значения — словари с топ-жанрами в этом десятилетии.
        """

        # Извлекаем годы и жанры
        data = self._get_data()
        decade_genres = defaultdict(list)

        for row in data:
            title = row[1].strip('"')
            genres_str = row[2].replace('"', '')
            genres_list = genres_str.split('|')

            # Извлекаем год из названия
            year = None
            if title[-1] == '"' or title[-1] == "'":
                year = title[-6:-2]
            else:
                year = title[-5:-1]

            if year.isdigit():
                decade = f"{year[:3]}0s" 
            else:
                decade = "unknown"

            decade_genres[decade].extend(genres_list)

        result = {}
        for decade, genres_list in decade_genres.items():
            top_genres = dict(Counter(genres_list).most_common(5)) 
            result[decade] = top_genres

        return result


    def dist_by_release(self):
        """
        The method returns a dict or an OrderedDict where the keys are years and the values are counts.
        You need to extract years from the titles. Sort it by counts descendingly.
        """
        data = self._get_data()
        years = []
        for line in data:
            year = line[1]
            if year[-1] == '"' or year[-1] == "'":
                year = year[-6:-2]
            else:
                year = year[-5:-1]
            if year.isdigit():
                years.append(year)
            else:
                years.append("unknown year")

        return dict(Counter(years).most_common())

    def dist_by_genres(self):
        """
        The method returns a dict where the keys are genres and the values are counts.
     Sort it by counts descendingly.
        """
        data = self._get_data()
        allgenres = []
        for line in data:
            # Жанры в третьем столбце, разделены |
            genres_str = line[2]
            genres_str = genres_str.replace('"', '')
            genres_list = genres_str.split('|')
            allgenres.extend(genres_list)

        return dict(Counter(allgenres).most_common())

    def most_genres(self, n):
        """
        The method returns a dict with top-n movies where the keys are movie titles and
        the values are the number of genres of the movie. Sort it by numbers descendingly.
        """
        data = self._get_data()
        movie_genres_count = {}

        for row in data:
            title = row[1].strip('"')
            genres_str = row[2].replace('"', '')

            count = len(genres_str.split('|'))
            movie_genres_count[title] = count

        sorted_movies = Counter(movie_genres_count).most_common(n)
        return dict(sorted_movies)
    

class Ratings:
    """
    Analyzing data from ratings.csv
    """

    def __init__(self, path_to_the_file, path_to_the_movies):
        if not os.path.exists(path_to_the_file):
            raise FileNotFoundError(f"Файл {path_to_the_file} не существует")
        self.path = path_to_the_file
        self.data = self._get_data()
        self.moviespath = path_to_the_movies
        self.moviesdata = self._get_movies()

    def _get_data(self):
        """
        Reads the first 1000 lines of ratings.csv
        Returns a list of dicts or tuples for easier processing.
        Format: [{'userId': str, 'movieId': str, 'rating': float, 'timestamp': int}, ...]
        """
        data = []
        with open(self.path, 'r', encoding='utf-8') as file:
            next(file)  # Skip header
            for i, line in enumerate(file):
                if i >= 1000:  # Limit 1000
                    break

                line = line.strip()
                parts = line.split(',')
                if len(parts) == 4:
                    data.append({
                        'userId': parts[0],
                        'movieId': parts[1],
                        'rating': float(parts[2]),
                        'timestamp': int(parts[3])
                    })
        return data

    def _get_movies(self):
        """
        Returns dict using movies.csv with pairs {movieId: title}
        """
        data = {}
        with open(self.moviespath, 'r', encoding='utf-8') as file:
            next(file)  # Skip header
            for  line in file:
                line = line.strip()
                parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)
                if len(parts) >= 2:
                    movie_id = parts[0]
                    title = parts[1].strip('"')  # Убираем лишние кавычки
                    data[movie_id] = title
        return data

    class Movies:
        def __init__(self, data, moviesdata):
            self.data = data
            # По умолчанию группируем по ID фильма
            self.group_by_key = 'movieId'
            self.moviesdata = moviesdata

        @staticmethod
        def average(values):
            return sum(values) / len(values)

        @staticmethod
        def median(values):
            sorted_v = sorted(values)
            n = len(sorted_v)
            mid = n // 2
            if n % 2 == 0:
                return (sorted_v[mid - 1] + sorted_v[mid]) / 2
            else:
                return sorted_v[mid]

        @staticmethod
        def variance(values):
            mean = sum(values) / len(values)
            return sum((x - mean) ** 2 for x in values) / len(values)

        def _get_grouped_ratings(self):
            groups = defaultdict(list)
            for row in self.data:
                key = row[self.group_by_key]# Используем текущий ключ (movieId или userId)
                if self.group_by_key == 'movieId':
                    # .get(key, key) вернет ID, если названия нет в словаре (безопасно)
                    key = self.moviesdata.get(key, key)

                groups[key].append(row['rating'])
            return groups



        def dist_by_year(self):
            """
            The method returns a dict where the keys are years and the values are counts.
            Sort it by years ascendingly. You need to extract years from timestamps.
            """

            years = [datetime.datetime.fromtimestamp(row['timestamp']).year for row in self.data]
            return dict(sorted(Counter(years).items()))

        def dist_by_rating(self):
            """
            The method returns a dict where the keys are ratings and the values are counts.
         Sort it by ratings ascendingly.
            """
            ratings = [row['rating'] for row in self.data]
            return dict(sorted(Counter(ratings).items()))

        def top_by_num_of_ratings(self, n):
            """
            The method returns top-n movies by the number of ratings.
            It is a dict where the keys are movie titles and the values are numbers.
     Sort it by numbers descendingly.
            """
            movies = [row[self.group_by_key] for row in self.data]
            if self.group_by_key == 'movieId':
                movies = [self.moviesdata[row] for row in movies]
            return dict(Counter(movies).most_common(n))

        def top_by_ratings(self, n, metric=None):
            """
            The method returns top-n movies by the average or median of the ratings.
            It is a dict where the keys are movie titles and the values are metric values.
            Sort it by metric descendingly.
            The values should be rounded to 2 decimals.
            """
            if metric is None:
                metric = self.average

            grouped = self._get_grouped_ratings()
            calculated = {k: round(metric(v), 2) for k, v in grouped.items()}

            return dict(sorted(calculated.items(), key=lambda item: item[1], reverse=True)[:n])

        def top_controversial(self, n):
            """
            The method returns top-n movies by the variance of the ratings.
            It is a dict where the keys are movie titles and the values are the variances.
          Sort it by variance descendingly.
            The values should be rounded to 2 decimals.
            """
            grouped = self._get_grouped_ratings()
            calculated = {k: round(self.variance(v), 2) for k, v in grouped.items()}

            return dict(sorted(calculated.items(), key=lambda item: item[1], reverse=True)[:n])

    class Users(Movies):
        """
        In this class, three methods should work.
        The 1st returns the distribution of users by the number of ratings made by them.
        The 2nd returns the distribution of users by average or median ratings made by them.
        The 3rd returns top-n users with the biggest variance of their ratings.
     Inherit from the class Movies. Several methods are similar to the methods from it.
        """

        def __init__(self, data, moviesdata):
            super().__init__(data, moviesdata)
            self.group_by_key = 'userId'



    @property
    def movies(self):
        return self.Movies(self.data, self.moviesdata)

    @property
    def users(self):
        return self.Users(self.data, self.moviesdata)
    
        

class Tags:
    """
    Analyzing data from tags.csv
    """

    def __init__(self, path_to_the_file):
        if not os.path.exists(path_to_the_file):
            raise FileNotFoundError(f"Файл {path_to_the_file} не существует")
        self.path = path_to_the_file
        # Читаем данные один раз при старте
        self.data = self._get_data()

    def _get_data(self):
        """
        Читаем файл, соблюдая лимит 1000 строк и правильно обрабатывая кавычки.
        Возвращает список тегов (просто список строк).
        """
        tags_list = []
        with open(self.path, 'r', encoding='utf-8') as file:
            next(file)  # Пропуск заголовка

            for i, line in enumerate(file):
                if i >= 1000:  # Лимит задания
                    break

                line = line.strip()
                # Используем тот же Regex, что и в Movies, чтобы не ломать строки с запятыми
                parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)

                # tags.csv: userId,movieId,tag,timestamp
                # Нас интересует tag (индекс 2)
                if len(parts) >= 3:
                    tag = parts[2]
                    # Убираем лишние кавычки, если они были вокруг тега
                    tag = tag.strip('"')
                    tags_list.append(tag)
        return tags_list

    def _get_tags_with_movie_ids(self):
        """
        Возвращает список кортежей: [(movieId, tag), ...].
        Используется для методов, требующих связь тегов и фильмов.
        """
        tags_list = []
        with open(self.path, 'r', encoding='utf-8') as file:
            next(file)  # Пропуск заголовка

            for i, line in enumerate(file):
                if i >= 1000:  # Лимит задания
                    break

                line = line.strip()
                parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)

                # tags.csv: userId,movieId,tag,timestamp
                # Нас интересует movieId (индекс 1) и tag (индекс 2)
                if len(parts) >= 3:
                    movie_id = parts[1]
                    tag = parts[2].strip('"')  # Убираем лишние кавычки
                    tags_list.append((movie_id, tag))
        return tags_list


    def most_words(self, n):
        """
        The method returns top-n tags with most words inside. It is a dict
 where the keys are tags and the values are the number of words inside the tag.
 Drop the duplicates. Sort it by numbers descendingly.
        """
        unique_tags = list(set(self.data))

        counted_words = {tag: len(re.findall(r'\w+', tag)) for tag in unique_tags}

        sorted_items = sorted(counted_words.items(), key=lambda item: item[1], reverse=True)
        return dict(sorted_items[:n])

    def longest(self, n):
        """
        The method returns top-n longest tags in terms of the number of characters.
        It is a list of the tags. Drop the duplicates. Sort it by numbers descendingly.
        """
        unique_tags = list(set(self.data))

        # Сортируем по длине строки
        sorted_tags = sorted(unique_tags, key=len, reverse=True)

        return sorted_tags[:n]

    def most_words_and_longest(self, n):
        """
        The method returns the intersection between top-n tags with most words inside and
        top-n longest tags in terms of the number of characters.
        Drop the duplicates. It is a list of the tags.
        """
        most_words_tags = set(self.most_words(n).keys())
        longest_tags = set(self.longest(n))

        intersection = list(most_words_tags & longest_tags)
        return intersection

    def most_popular(self, n):
        """
        The method returns the most popular tags.
        It is a dict where the keys are tags and the values are the counts.
        Drop the duplicates. Sort it by counts descendingly.
        """
        return dict(Counter(self.data).most_common(n))

    def tags_with(self, word):
        """
        The method returns all unique tags that include the word given as the argument.
        Drop the duplicates. It is a list of the tags. Sort it by tag names alphabetically.
        """
        unique_tags = set(self.data)
        tags_with_word = [tag for tag in unique_tags if word in tag]
        return sorted(tags_with_word)


DATASETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'datasets')
PATH_MOVIES = os.path.join(DATASETS_DIR, 'movies.csv')
PATH_RATINGS = os.path.join(DATASETS_DIR, 'ratings.csv')
PATH_TAGS = os.path.join(DATASETS_DIR, 'tags.csv')
PATH_LINKS = os.path.join(DATASETS_DIR, 'links.csv')

# --- 1. Тесты для класса Movies ---
class TestMovies:
    @pytest.fixture
    def movies(self):
        return Movies(PATH_MOVIES)

    def test_dist_by_release(self, movies):
        res = movies.dist_by_release()
        assert isinstance(res, dict), "Должен возвращать словарь"
        # Проверка типов
        first_key = next(iter(res))
        first_val = res[first_key]
        assert isinstance(first_key, str), "Год должен быть строкой"
        assert isinstance(first_val, int), "Количество должно быть int"
        # Проверка сортировки (по убыванию количества)
        values = list(res.values())
        assert values == sorted(values, reverse=True), "Должно быть отсортировано по убыванию (counts)"

    def test_dist_by_genres(self, movies):
        res = movies.dist_by_genres()
        assert isinstance(res, dict)
        # Проверка типов
        first_key = next(iter(res))
        assert isinstance(first_key, str), "Жанр должен быть строкой"
        # Проверка сортировки (по убыванию)
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_most_genres(self, movies):
        n = 10
        res = movies.most_genres(n)
        assert isinstance(res, dict)
        assert len(res) <= n
        # Проверка сортировки (по убыванию)
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_top_genres_by_decade(self, movies):
        res = movies.top_genres_by_decade()
        assert isinstance(res, dict)
        # Проверяем, что значения - тоже словари (жанр: количество)
        for decade, genres in res.items():
            assert isinstance(genres, dict)
            for genre, count in genres.items():
                assert isinstance(genre, str)
                assert isinstance(count, int)

# --- 2. Тесты для класса Ratings ---
class TestRatings:
    @pytest.fixture
    def ratings(self):
        # ВАЖНО: Теперь передаем два пути!
        if not os.path.exists(PATH_MOVIES):
            pytest.skip("movies.csv not found. Skipping Ratings tests.")
        return Ratings(PATH_RATINGS, PATH_MOVIES)

    # -- Movies Subclass --
    def test_movies_dist_by_year(self, ratings):
        res = ratings.movies.dist_by_year()
        assert isinstance(res, dict)
        keys = list(res.keys())
        assert keys == sorted(keys)

    def test_movies_dist_by_rating(self, ratings):
        res = ratings.movies.dist_by_rating()
        assert isinstance(res, dict)
        keys = list(res.keys())
        assert keys == sorted(keys)

    def test_movies_top_by_ratings(self, ratings):
        res = ratings.movies.top_by_ratings(5)
        assert isinstance(res, dict)
        # Проверяем, что ключи - это строки (названия фильмов), а не ID
        first_key = next(iter(res))
        # ID обычно цифры ("1"), название - буквы ("Toy Story")
        # Это не строгая проверка, но для примера пойдет
        assert isinstance(first_key, str)
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_movies_top_by_num_of_ratings(self, ratings):
        res = ratings.movies.top_by_num_of_ratings(5)
        assert isinstance(res, dict)
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_movies_top_controversial(self, ratings):
        res = ratings.movies.top_controversial(5)
        assert isinstance(res, dict)
        values = list(res.values())
        assert values == sorted(values, reverse=True)


    # -- Users Subclass --
    def test_users_top_by_num_of_ratings(self, ratings):
        res = ratings.users.top_by_num_of_ratings(5)
        assert isinstance(res, dict)
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_users_top_by_ratings(self, ratings):
        res = ratings.users.top_by_ratings(5)
        assert isinstance(res, dict)
        first_key = next(iter(res))
        assert isinstance(first_key, str)
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_users_top_controversial(self, ratings):
        res = ratings.users.top_controversial(5)
        assert isinstance(res, dict)
        values = list(res.values())
        assert values == sorted(values, reverse=True)



# --- 3. Тесты для класса Tags ---
class TestTags:
    @pytest.fixture
    def tags(self):
        return Tags(PATH_TAGS)
    
    @pytest.fixture
    def ratings(self):
        if not os.path.exists(PATH_MOVIES):
            pytest.skip("movies.csv not found. Skipping Ratings tests.")
        return Ratings(PATH_RATINGS, PATH_MOVIES)

    def test_most_words(self, tags):
        res = tags.most_words(5)
        assert isinstance(res, dict)
        # Сортировка по кол-ву слов убыванию
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_longest(self, tags):
        res = tags.longest(5)
        assert isinstance(res, list), "Должен возвращать список"
        assert isinstance(res[0], str)
        # Сортировка по длине строки убыванию
        lengths = [len(t) for t in res]
        assert lengths == sorted(lengths, reverse=True)

    def test_most_words_and_longest(self, tags):
        res = tags.most_words_and_longest(5)
        assert isinstance(res, list)
        # Все элементы должны быть в top-5 по словам и длине
        most_words_keys = set(tags.most_words(5).keys())
        longest_list = set(tags.longest(5))
        assert set(res) == most_words_keys & longest_list

    def test_most_popular(self, tags):
        res = tags.most_popular(5)
        assert isinstance(res, dict)
        # Сортировка по популярности убыванию
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_tags_with(self, tags):
        res = tags.tags_with('funny')
        assert isinstance(res, list)
        # Сортировка АЛФАВИТНАЯ
        assert res == sorted(res)



# --- 4. Тесты для класса Links ---
class TestLinks:
    @pytest.fixture
    def links(self):

        # Проверка наличия movies.csv (теперь он нужен для Links)
        if not os.path.exists(PATH_MOVIES):
            pytest.skip("movies.csv not found. Skipping Links tests.")

        # ОБНОВЛЕНИЕ ЗДЕСЬ: Передаем два пути в конструктор
        return Links(PATH_LINKS, PATH_MOVIES)

    def test_top_directors(self, links):
        res = links.top_directors(3)
        assert isinstance(res, dict)
        # Проверка сортировки по убыванию
        values = list(res.values())
        assert values == sorted(values, reverse=True)

    def test_most_expensive(self, links):
        res = links.most_expensive(3)
        assert isinstance(res, dict)
        # Значения должны быть числами (бюджет)
        if res:
            first_val = next(iter(res.values()))
            assert isinstance(first_val, (int, float))
            values = list(res.values())
            assert values == sorted(values, reverse=True)

    def test_get_imdb(self, links):
        list_of_movies = ['1', '2', '3']
        list_of_fields = ['Director', 'Budget', 'Title']

        res = links.get_imdb(list_of_movies, list_of_fields)

        assert isinstance(res, list)
        assert len(res) > 0
        for row in res:
            assert isinstance(row, list)
            assert len(row) == len(list_of_fields) + 1
            assert isinstance(row[0], str)
        # Проверка сортировки по movieId убыванию
        movie_ids = [int(row[0]) for row in res]
        assert movie_ids == sorted(movie_ids, reverse=True)

    def test_longest(self, links):
        res = links.longest(3)
        assert isinstance(res, dict)
        if res:
            values = list(res.values())
            assert values == sorted(values, reverse=True)

    def test_top_cost_per_minute(self, links):
        res = links.top_cost_per_minute(3)
        assert isinstance(res, dict)
        if res:
            values = list(res.values())
            assert values == sorted(values, reverse=True)

    def test_roi_by_director(self, links):
        res = links.roi_by_director(3)
        assert isinstance(res, dict)
        # Проверяем, что все значения - числа (ROI)
        if res:
            for roi in res.values():
                assert isinstance(roi, float)
            # Проверяем сортировку по убыванию
            values = list(res.values())
            assert values == sorted(values, reverse=True)

    def test_most_profitable(self, links):
        res = links.most_profitable(3)
        assert isinstance(res, dict)
        if res:
            values = list(res.values())
            assert values == sorted(values, reverse=True)


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ КРАСИВОГО ВЫВОДА ---

def print_top(data, title="Топ", unit=""):
    """
    Выводит данные в виде красивой текстовой таблицы.
    НЕ СОРТИРУЕТ данные, выводит в том порядке, в котором они переданы.
    """
    print(f"\n🏆 {title}")
    print("=" * 50)

    if isinstance(data, dict):
        # Просто перебираем словарь.
        for i, (key, value) in enumerate(data.items(), 1):
            # Красивое форматирование чисел
            if isinstance(value, float):
                val_str = f"{value:,.2f}"
            elif isinstance(value, int):
                val_str = f"{value:,}"
            else:
                val_str = str(value)

            print(f"{i}. {str(key):<30} | {val_str} {unit}")

    elif isinstance(data, list):
        for i, item in enumerate(data, 1):
            print(f"{i}. {item}")

    print("=" * 50)


def plot_ascii_bar(data, title="График"):
    """
    Рисует текстовую гистограмму.
    НЕ СОРТИРУЕТ данные. Берет первые 15 элементов словаря как есть.
    """
    print(f"\n📊 {title}")
    print("-" * 50)
    if not data:
        print("Нет данных для отображения")
        return

    # Превращаем items() в список и режем его
    sliced_items = list(data.items())[:15]

    # Находим максимум для масштабирования
    try:
        # Ищем максимум среди значений выбранных 15 элементов
        max_val = max(val for _, val in sliced_items)
    except ValueError:
        max_val = 1

    scale = 25  # Максимальная длина полоски в символах

    for key, value in sliced_items:
        # Вычисляем длину бара
        if max_val > 0:
            bar_len = int((value / max_val) * scale)
        else:
            bar_len = 0

        bar = "█" * bar_len

        if isinstance(value, float):
            val_str = f"{value:,.2f}"  # Показываем 2.44
        else:
            val_str = f"{value:,}"  # Показываем 2

        print(f"{str(key)[:20]:<20} | {bar} ({val_str})")

    print("-" * 50)