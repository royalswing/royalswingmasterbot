import json
import telegram
import os
import logging
from datetime import datetime
from telegram import ParseMode
from geopy.geocoders import Nominatim

import boto3
dynamodb = boto3.resource('dynamodb')

# Logging is cool!
logger = logging.getLogger()
if logger.handlers:
    for handler in logger.handlers:
        logger.removeHandler(handler)
logging.basicConfig(level=logging.INFO)

OK_RESPONSE = {
    'statusCode': 200,
    'headers': {'Content-Type': 'application/json'},
    'body': json.dumps('ok')
}
ERROR_RESPONSE = {
    'statusCode': 400,
    'body': json.dumps('Oops, something went wrong!')
}

TABLE_USER_ITEM = {
    'chat_id': False,
    'private_group_chat_id': False,
    'username': False,
    'first_name': False,
    'last_name': False,
    'sex': False,
    'lon': False,
    'lat': False,
    'phone': False,
    'real_name': False,
    'birthday': False,
    'real_name_second': False,
    'birthday_second': False,
    'created_at': False,
    'updated_at': False,
}

# Вопросы для обогащения анкеты пользователя. Поочерёдные.
QUERY_TEXTS = {
    'how_is': {
        'message': '{}, привеееет! Очень рад, что вас заинтересовало наше сообщество. '
                   'Давайте для начала я идентифицирую вас. '
                   'Это нужно, чтобы определить вас в нужную группу.'
                   '\n\nКак вы знакомитесь (нажми ответ на одну из кнопок)?',
        'buttons': ['Я парень', 'Я девушка', 'Мы пара'],
    },
    'location': {
        'message': '{}, а теперь мне нужно знать откуда Вы, разрешите узнать ваше метоположение. '
                   'Для этого нажмите на кнопку (чтобы кнопка сработала, нужно это делать на мобильном устройстве).',
        'location_button': 'Поделиться текущим положением',
    },
    'contact': {
        'message': '{}, отлично! Осталось не много, для продолжения нужен ваш номер телефона. '
                   'Это не сложно, достаточно нажать на кнопку "Поделиться телефоном".',
        'contact_button': 'Поделиться телефоном',
    },
    'name': {
        'message': 'Часто бывает, что люди в Telegram пишуть странные ники, '
                   'которые другим участникам клуба сложно понять и соотнести с конкретным человеком. '
                   '\n\n{}, напишите своё имя.'
    },
    'name_first': {
        'message': 'Так как вы пара, то надо узнать как и кого зовут, {} напишите имя первой половинки:'
    },
    'name_second': {
        'message': 'А сейчас, {} напишите имя второй половинки:'
    },
    'birthday': {
        'message': '{}, чтобы мы вам могли дарить подарки и отправлять поздравления, '
                   'напишите дату своего рождения, например:  `29.02.2000`'
    },
    'birthday_couple': {
        # 'message': '{}, все прекрасно! Чтобы мы вам могли дарить отличные подарки для такой прекрасной пары, '
        #            'напишите свои дни рождения через пробел, первый для {}, а второй для {}, '
        #            'например: `28.08.1990 31.12.2001`'
        'message': '{}, все прекрасно! Чтобы мы вам могли дарить отличные подарки для такой прекрасной пары, '
                   'напишите свои дни рождения через пробел, '
                   'например: `28.08.1990 31.12.2001`'
    },
    'message_from_admin': {
        'message': '{}'
    }
}

# Ссылки на местные чаты
LINKS = [
    {
        'cities': ['Иркутск', 'Ангарск', 'Шелехов', 'Усолье'],
        'state': 'Иркутская',
        'chat_id': os.environ.get('TELEGRAM_IRKUTSK_CHAT_ID'),
    }
]


def configure_telegram():
    """
    Configures the bot with a Telegram Token.
    Returns a bot instance.
    """

    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    if not TELEGRAM_TOKEN:
        logger.error('The TELEGRAM_TOKEN must be set')
        raise NotImplementedError

    return telegram.Bot(TELEGRAM_TOKEN)


def reset(chat_id: int, item: dict, table) -> None:
    """
    Функция сброса данных пользователя.

    :param chat_id:
    :param item:
    :param table:
    """
    timestamp = str(datetime.utcnow().timestamp())
    new_item = TABLE_USER_ITEM
    new_item.update({
        'chat_id': chat_id,
        'private_group_chat_id': item['private_group_chat_id'],
        'updated_at': timestamp,
        'created_at': item['created_at']
    })
    table.put_item(Item=new_item)


def write_sex(chat_id: int, item: dict, table, text: str, **kwargs) -> bool:
    """
    Функция записывает данные по полу пользователя.

    :param chat_id:
    :param item:
    :param table:
    :param text:
    :return:
    """
    if item and item['sex']:
        return True

    if text == 'Я парень':
        sex = 'M'
    elif text == 'Я девушка':
        sex = 'F'
    elif text == 'Мы пара':
        sex = 'C'
    else:
        return False

    if not item:
        item = TABLE_USER_ITEM

    timestamp = str(datetime.utcnow().timestamp())
    item.update({
        'chat_id': chat_id,
        'sex': sex,
        'updated_at': timestamp,
    })

    if kwargs:
        item.update(**kwargs)

    if item and item.get('created_at'):
        item.update({
            'created_at': timestamp,
        })

    table.put_item(Item=item)
    return True


def write_location(chat_id: int, item: dict, table, message: object) -> bool:
    """
    Метод сохранения локации пользователя, для нас по сути важен только город в котором пользователь живет
    или ближайший доступный город в котором проводятся вечеринки.

    :param chat_id: Идентификатор чата
    :param item: Данные о пользователе из БД
    :param table: Таблица в БД
    :param message: Объект сообщения пользователя
    :return: Булевое значение результата сохранения
    """
    if item['lon'] and item['lat']:
        return True

    if hasattr(message, 'location'):
        location = message.location
        if hasattr(location, 'longitude') and hasattr(location, 'latitude'):
            timestamp = str(datetime.utcnow().timestamp())
            item.update({
                'chat_id': chat_id,
                'lon': str(location.longitude),
                'lat': str(location.latitude),
                'updated_at': timestamp
            })
            table.put_item(Item=item)
            return True
    return False


def write_contact(chat_id: int, item: dict, table, message: object) -> bool:
    """
    Метод сохранения контактных данных пользователя.

    :param chat_id: Идентификатор чата
    :param item: Данные о пользователе из БД
    :param table: Таблица в БД
    :param message: Объект сообщения пользователя
    :return: Булевое значение результата сохранения
    """
    if item['phone']:
        return True

    if hasattr(message, 'contact'):
        contact = message.contact
        if hasattr(contact, 'phone_number'):
            timestamp = str(datetime.utcnow().timestamp())
            item.update({
                'chat_id': chat_id,
                'phone': contact.phone_number,
                'first_name': contact.first_name,
                'last_name': contact.last_name,
                'updated_at': timestamp
            })
            table.put_item(Item=item)
            return True
    return False


def write_name(chat_id: int, item: dict, table, text: str, field: str = 'real_name') -> bool:
    """
    Универсальный метод сохранения имени пользователя или имен пары.

    :param chat_id: Идентификатор чата
    :param item: Данные о пользователе из БД
    :param table: Таблица в БД
    :param text: Полученный от пользователя текст
    :param field: Обновляемое поле
    :return: Булевое значение результата сохранения
    """
    if item[field]:
        return True

    timestamp = str(datetime.utcnow().timestamp())
    item.update({
        'chat_id': chat_id,
        field: text,
        'updated_at': timestamp
    })
    table.put_item(Item=item)
    return True


def write_birthday(chat_id: int, item: dict, table, text: str) -> bool:
    """
    Универсальный метод записи дня рождения пользователя или пары.

    :param chat_id: Идентификатор чата
    :param item: Данные о пользователе из БД
    :param table: Таблица в БД
    :param text: Полученный от пользователя текст
    :return: Булевое значение результата сохранения
    """
    birthday = [text]
    if item['sex'] == 'C':
        if item['birthday'] and item['birthday_second']:
            return True
        birthday = text.split(' ', 1)
    else:
        if item['birthday']:
            return True

    for i in range(len(birthday)):
        try:
            datetime.strptime(birthday[i], '%d.%m.%Y')
        except (ValueError, TypeError):
            return False
        if i == 0:
            item.update({'birthday': birthday[i]})
        else:
            item.update({'birthday_second': birthday[i]})

    timestamp = str(datetime.utcnow().timestamp())
    item.update({
        'chat_id': chat_id,
        'updated_at': timestamp
    })
    table.put_item(Item=item)
    return True


def send_quest(quest: dict, bot, chat_id: int) -> None:
    """
    Универсальный метод отправки сообщения пользовалю от бота.

    :param quest: Вопрос пользователю
    :param bot: Класс бота
    :param chat_id: Идентификатор чата
    """
    custom_keyboard = []
    reply_markup = None

    # проверим наличие в массиве обычных кнопок
    if quest.get('buttons'):
        for button in quest['buttons']:
            custom_keyboard.append(telegram.KeyboardButton(button))

    # проверим в массиве наличие кнопки запроса местоположения
    if quest.get('location_button'):
        custom_keyboard.append(telegram.KeyboardButton(quest['location_button'], request_location=True))

    # проверим в массиве наличие кнопки запроса контактов
    if quest.get('contact_button'):
        custom_keyboard.append(telegram.KeyboardButton(quest['contact_button'], request_contact=True))

    # добавим клавиатуру в сообщение пользователю
    if custom_keyboard:
        custom_keyboard = [custom_keyboard]
        reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard, one_time_keyboard=True)

    bot.sendMessage(chat_id, quest['message'], reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


def send_link(item: dict, bot, chat_id: int) -> None:
    geolocator = Nominatim(user_agent='RoyalSwingClub')
    location = geolocator.reverse('{}, {}'.format(item['lat'], item['lon']))
    address = location.raw['address']

    link = None
    for branch in LINKS:
        if address['city'] in branch['cities'] and branch['state'] in address['state']:
            group_chat_id = branch['chat_id']
            about_chat = bot.get_chat(group_chat_id)
            if not about_chat.invite_link:
                link = bot.export_chat_invite_link(group_chat_id)
            else:
                link = about_chat.invite_link
            break


    text = (
        'Итак, подведем итоги:\n\n'
        '\t- Вы знакомитесь как: {}\n'
        '\t- Ваш контактный номер телефона: +{}\n'
        '\t- Вы находитесь: {}, {}, {}\n'
    )
    if item['sex'] == 'C':
        text += (
            # '\t- Вы представились как: {} и {}\n'
            '\t- Ваши дни рождения: {} и {}\n\n'
        )
        text = text.format(
            'Пара',
            item['phone'],
            location.raw['address']['country'],
            location.raw['address']['state'],
            location.raw['address']['city'],
            # item['real_name'],
            # item['real_name_second'],
            item['birthday'],
            item['birthday_second'],
        )
    else:
        text += (
            # '\t- Вы представились как: {}\n'
            '\t- Ваш день рождения: {}\n\n'
        )
        text = text.format(
            ('Парень' if item['sex'] == 'M' else 'Девушка'),
            item['phone'],
            location.raw['address']['country'],
            location.raw['address']['state'],
            location.raw['address']['city'],
            # item['real_name'],
            item['birthday']
        )

    keyboard = [
        [telegram.InlineKeyboardButton('Общий чат Royal Swing', url='https://t.me/royal_swing_chat')],
        [telegram.InlineKeyboardButton('Официальный канал Royal Swing', url='https://t.me/royal_swing')],
    ]

    if link:
        text += 'Если все правильно, тогда кликай по кнопке и присоединяйся к закрытому чату.\n\n' \
                'А если требуется пригласить друга, подругу или пару, кидай им ссылку на меня: ' \
                'https://t.me/royalswingmasterbot\n\nА если нужно исправить какие-то данные, используй комманды, ' \
                'начни набирать в сообщении: `/`, появится список комманда с подсказками.'
        keyboard.insert(0, [telegram.InlineKeyboardButton('Иркутский чат Royal Swing', url=link)])
    else:
        text += (
            'К сожалению пока в вашем городе нет специального чата, но вы можете присоедениться к общему чату, '
            'в котором не менее интересно. А также читайте наш канал, может оказаться, '
            'что ваш город скоро появиться в списке. Сейчас у нас только:\n\n'
            '\t- Иркутск (Ангарск, Шелехов, Усолье-Сибирское)\n\n'
            'ВНИМАНИЕ! Мы предоставляем франшизу по тем города, которых нет в списке выше, '
            'напишите администратору @ArsenySokolov, если вы хотите проводить вечеринки в вашем городе.\n\n'
            'Также администратору можно написать, если вы из другого города, '
            'но тем не менее собираетесь приходить на вечеринки не в вашем городе.'
        )

    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    bot.sendMessage(
        chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


def calc_age(birthday: str) -> int:
    """
    Функция считает возраст пользователя.

    :param birthday: Дата рождения
    :return: Возраст по 0 часовому поясу
    """
    born = datetime.strptime(birthday, '%d.%m.%Y')
    today = datetime.utcnow().today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def age_with_suffix(age: int) -> str:
    k = age % 10
    if (age > 9) and (age < 20) or (age > 110) or (k > 4) or (k == 0):
        return '{} лет'.format(age)
    else:
        if k == 1:
            return '{} год'.format(age)
        else:
            return '{} года'.format(age)


def welcome_message(table, bot, chat_id: int, member_chat_id: int):
    result = table.get_item(Key={'chat_id': member_chat_id})
    item = result.get('Item')

    user_age = calc_age(item['birthday'])

    text = 'К нам присоеденил{} [{}](tg://user?id={}) ({}), давайте поприветствуем новичка!'

    if item['last_name']:
        full_name = '{} {}'.format(item['first_name'], item['last_name'])
    else:
        full_name = item['first_name']

    text = text.format(
        ('ся мужчина' if item['sex'] == 'M' else 'ась девушка'),
        full_name,
        member_chat_id,
        age_with_suffix(user_age),
    )
    if item['private_group_chat_id']:
        private_group_chat_ids = str(item['private_group_chat_id']).split(',')
        if str(chat_id) not in private_group_chat_ids:
            private_group_chat_ids.append(str(chat_id))
            private_group_chat_id = ','.join(private_group_chat_ids)
        else:
            private_group_chat_id = item['private_group_chat_id']
    else:
        private_group_chat_id = str(chat_id)

    if item['private_group_chat_id'] != private_group_chat_id:
        timestamp = str(datetime.utcnow().timestamp())
        item.update({
            'private_group_chat_id': private_group_chat_id,
            'updated_at': timestamp
        })
        table.put_item(Item=item)

    bot.sendMessage(chat_id, text, parse_mode=ParseMode.MARKDOWN)


def webhook(event, context):
    """
    Runs the Telegram webhook.
    """

    bot = configure_telegram()
    logger.info('Event: {}'.format(event))

    if event.get('httpMethod') == 'POST' and event.get('body'):
        logger.info('==========> Message received <==========')
        update = telegram.Update.de_json(json.loads(event.get('body')), bot)
        logger.info('Message: {}'.format(update.message))

        if not update.message:
            # На случай пустных сообщений, зачем они вообще нужны???
            return OK_RESPONSE

        chat_id = update.message.chat.id
        custom_chat_id = None
        text = update.message.text
        chat_type = update.message.chat.type

        # получим нужную нам таблицу
        table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

        # обработка пользовательских данных, доступна только в приватном режиме общения.
        if chat_type == 'private':
            quest = None

            # получаем данные по текущему пользователю
            result = table.get_item(
                Key={
                    'chat_id': chat_id
                }
            )
            item = result.get('Item')
            logger.info('Item: {}'.format(item))

            # данные пользователя Telegram
            username = update.message.chat.username
            first_name = update.message.chat.first_name
            last_name = update.message.chat.last_name
            if last_name:
                full_name = '{} {}'.format(first_name, last_name)
            else:
                full_name = first_name

            # построим список администраторов
            admins = os.environ.get('TELEGRAM_ADMINS_CHAT_ID').split(',')

            # проверим команду сбороса данных
            if text == '/reset':
                reset(chat_id, item, table)
                quest = QUERY_TEXTS['how_is']
                quest['message'] = quest['message'].format(full_name)
            elif str(text).startswith('/sendmessage') and str(chat_id) in admins:
                full_text = str(text[12:]).strip()
                custom_chat_id, admin_text = full_text.split('|', 1)
                logger.info('Custom Chat Id: {}'.format(custom_chat_id))
                logger.info('Admin text: {}'.format(admin_text))
                quest = QUERY_TEXTS['message_from_admin']
                quest['message'] = quest['message'].format(admin_text)
            elif str(text).startswith('/revokeinvitelink') and str(chat_id) in admins:
                cities = []
                for branch in LINKS:
                    bot.export_chat_invite_link(branch['chat_id'])
                    cities.append(branch['cities'][0])
                quest = dict()
                cities = ', '.join(cities)
                quest['message'] = 'Ссылки-приглашения изменены для следующих регионов: {}'.format(cities)
            elif str(text).startswith('/getuser') and str(chat_id) in admins:
                quest = dict()
                _result = table.get_item(Key={'chat_id': int(text[8:])})
                if _result.get('Item'):
                    _item = _result.get('Item')
                    _full_name = '{} {}'.format(_item['first_name'], _item['last_name'])
                    quest['message'] = '[{}](tg://user?id={})'.format(_full_name, _item['chat_id'])
                else:
                    quest['message'] = 'Пользователь с таким идентификатором не найден :('

            # проверяем и заполняем данные пользователя
            if not write_sex(chat_id, item, table, text, username=username, first_name=first_name, last_name=last_name):
                # зададим первый вопрос пользователю
                quest = QUERY_TEXTS['how_is']
                quest['message'] = quest['message'].format(full_name)
            elif not write_location(chat_id, item, table, update.message):
                # узнаем где распололжен пользователь, нам это требуется для определения
                # в закрытую гео-группу клуба
                quest = QUERY_TEXTS['location']
                quest['message'] = quest['message'].format(full_name)
            elif not write_contact(chat_id, item, table, update.message):
                # узнаем номер телефона пользователя, т.к. телега предлагает отправку номера телефону будем
                # пользоваться этой опцией, ввиду того, что данный номер телефона уже проверен телегой.
                quest = QUERY_TEXTS['contact']
                quest['message'] = quest['message'].format(full_name)
            elif not item['sex'] == 'C':
                # if not item['real_name']:
                #     # узнаем реальное имя пользователья
                #     quest = QUERY_TEXTS['name']
                #     quest['message'] = quest['message'].format(first_name)
                #     write_name(chat_id, item, table, text)
                #     webhook(event, context)
                # elif not write_birthday(chat_id, item, table, text):
                if not write_birthday(chat_id, item, table, text):
                    # узнаем у пользователя дату рождения
                    quest = QUERY_TEXTS['birthday']
                    quest['message'] = quest['message'].format(full_name)
            else:
                # if not item['real_name']:
                #     # узнаем реальное имя пользователья
                #     quest = QUERY_TEXTS['name_first']
                #     quest['message'] = quest['message'].format(first_name)
                #     write_name(chat_id, item, table, text)
                #     webhook(event, context)
                # elif not item['real_name_second']:
                #     # узнаем реальное имя второй половинки
                #     quest = QUERY_TEXTS['name_second']
                #     quest['message'] = quest['message'].format(first_name)
                #     write_name(chat_id, item, table, text, 'real_name_second')
                #     webhook(event, context)
                # elif not write_birthday(chat_id, item, table, text):
                if not write_birthday(chat_id, item, table, text):
                    # узнаем у пользователя даты рождения обоих людей
                    quest = QUERY_TEXTS['birthday_couple']
                    # quest['message'] = quest['message'].format(
                    #     first_name,
                    #     item['real_name'],
                    #     item['real_name_second'],
                    # )
                    quest['message'] = quest['message'].format(full_name)

            if quest:
                _chat_id = chat_id
                if custom_chat_id:
                    _chat_id = int(custom_chat_id)
                send_quest(quest, bot, _chat_id)
            else:
                send_link(item, bot, chat_id)
        elif chat_type == 'supergroup':
            # составим список доступных региональных групп
            groups = []
            for link in LINKS:
                groups.append(link['chat_id'])

            if str(chat_id) in groups:
                if hasattr(update.message, 'new_chat_members'):
                    for new_chat_member in update.message.new_chat_members:
                        welcome_message(table, bot, chat_id, new_chat_member['id'])

        return OK_RESPONSE

    return ERROR_RESPONSE


def set_webhook(event, context):
    """
    Sets the Telegram bot webhook.
    """

    logger.info('Event: {}'.format(event))
    bot = configure_telegram()
    url = 'https://{}/{}/'.format(
        event.get('headers').get('Host'),
        event.get('requestContext').get('stage'),
    )
    webhook = bot.set_webhook(url)

    if webhook:
        return OK_RESPONSE

    return ERROR_RESPONSE
