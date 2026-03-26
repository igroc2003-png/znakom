package main

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"io"
	"os"
	"os/signal"
	"strconv" // ДОБАВЛЕНО
	"syscall"
	"time" // ДОБАВЛЕНО
	"strings"
	"math/rand"
	"net/http"
	"bytes"
	"encoding/json"
	"encoding/base64"
	"sync"
	

	
    
    maxbot "github.com/max-messenger/max-bot-api-client-go"
    "github.com/max-messenger/max-bot-api-client-go/schemes"

    _ "github.com/mattn/go-sqlite3"
)
//# ================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==================
const GEO_DB = "geo.db"
const DB_FILE = "bot.db"
const SUPPORT_URL = "https://max.ru/u/f9LHodD0cOKiKzr7C6wGuyRkZ-dyLuqHqXoQ1IxbhnV0yhJ9DLfhXrjZIfw"
const ADMIN_ID int64 = 198191393
const BOT_USERNAME = "id420105283818_1_bot"
const YOOKASSA_SHOP_ID = "1262924"
const YOOKASSA_SECRET_KEY = "live_vhNMjcNeJhnHG0HcBFjCXV1c97DM3Wbgi1Eg-ZHyLmA"
const RETURN_URL = "https://max.ru/id420105283818_1_bot"


// ================== БАЗЫ ДАННЫХ ==================

// Основная база бота (profiles, рулетка и т.д.)
var db *sql.DB

// База городов
var geoDB *sql.DB

func init() {
	var err error

	// Открываем geo.db (города)
	geoDB, err = sql.Open("sqlite3", GEO_DB)
	if err != nil {
		log.Fatal("Не удалось открыть базу geo.db:", err)
	}
}



















// ================== ТАРИФЫ ==================

var TARIFFS = map[string]struct {
	Name  string
	Price int
	Days  int
}{
	"vip_30":  {"VIP 30 дней", 300, 30},
	"vip_180": {"VIP 6 месяцев", 1500, 180},
	"vip_365": {"VIP 12 месяцев", 2500, 365},
}

// ================== ПЛАТЕЖИ (YooKassa) ==================

// Контексты API для пользователей (если нужно отправлять ответ позже)
//var contexts = map[int64]*maxbot.Api{}

// Ответ от YooKassa
type YooPayment struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Paid   bool   `json:"paid"`

	Confirmation struct {
		ConfirmationURL string `json:"confirmation_url"`
	} `json:"confirmation"`
}

// Сумма платежа
type Amount struct {
	Value    string `json:"value"`
	Currency string `json:"currency"`
}

// Подтверждение оплаты
type Confirmation struct {
	Type      string `json:"type"`
	ReturnURL string `json:"return_url"`
}

// Запрос на создание платежа
type PaymentRequest struct {
	Amount       Amount                 `json:"amount"`
	Capture      bool                   `json:"capture"`
	Description  string                 `json:"description"`
	Confirmation Confirmation           `json:"confirmation"`
	Metadata     map[string]interface{} `json:"metadata"`
}

// Ответ от API платежа
type PaymentResponse struct {
	ID     string `json:"id"`
	Status string `json:"status"`

	Confirmation struct {
		Type string `json:"type"`
		URL  string `json:"confirmation_url"`
	} `json:"confirmation"`
}

// ================== СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ ==================

type UserState struct {
	ChatID int64

	// ===== Анкета =====
	Name       string
	Gender     string
	BirthDay   int
	BirthMonth int
	BirthYear  int
	Birthdate  string
	Age        int
	Zodiac     string

	City   string
	Region string
	Tz     string // часовой пояс

	About    string
	Photo    *schemes.PhotoTokens
	PhotoURL string

	// ===== Состояния =====
	Step            string
	IsEditing       bool
	EditingExisting bool
	ReturnKeyboard  string
	Mode            string

	// ===== Флаги =====
	anketa    bool
	IsVIP     bool
	VIP       bool
	DeletedAt int64

	// ===== Фильтры =====
	FilterCity   string
	FilterGender string
	FilterAgeMin int
	FilterAgeMax int
}

// ================== ГЛОБАЛЬНЫЕ ХРАНИЛИЩА ==================

var (
	users = map[int64]*UserState{}

	tz string

	// ===== Рулетка =====
	rouletteQueue = []int64{}
	activeChats   = map[int64]int64{}
	userContexts  = map[int64]*maxbot.Api{}

	mu = &sync.Mutex{}

	lastActivityCache = map[int64]int64{}
)

// ================== ФИЛЬТРЫ ==================

type Filters struct {
	City   string
	Region string
	Gender string
	AgeMin int
	AgeMax int
}

// ================== КОНСТАНТЫ ==================

const (
	MinAgeLimit = 18
	MaxAgeLimit = 100
)

// ================== СТАТИСТИКА ==================

type Stats struct {
	UsersTotal int
	UsersM     int
	UsersF     int

	VIPTotal int
	VIPM     int
	VIPF     int

	Online int

	WaitingQueue int
	ActiveChats  int

	TotalSearches int
	TotalMatches  int
}

// ================== ВСПОМОГАТЕЛЬНЫЕ СТРУКТУРЫ ==================

// Контекст для универсальных функций (например выбор города)
type Context struct {
	ChatID  int64
	API     *maxbot.Api
	Payload string
}

// Вложение (например фото)
type Attachment struct {
	Payload struct {
		URL string
	}
}

// Город
type City struct {
	Name   string
	Region string
}






































// ================== ОТПРАВКА СООБЩЕНИЯ ==================

// Reply — метод для отправки сообщения с клавиатурой
func (c *Context) Reply(text string, keyboard ...*maxbot.Keyboard) {
	msg := maxbot.NewMessage()
	msg.SetChat(c.ChatID)
	msg.SetText(text)

	if len(keyboard) > 0 {
		for _, k := range keyboard {
			msg.AddKeyboard(k)
		}
	}

	c.API.Messages.Send(context.Background(), msg)
}

// ================== УТИЛИТЫ ==================

// Определение знака зодиака
func getZodiac(day int, month int) string {
	switch {
	case (month == 3 && day >= 21) || (month == 4 && day <= 19):
		return "♈ Овен"
	case (month == 4 && day >= 20) || (month == 5 && day <= 20):
		return "♉ Телец"
	case (month == 5 && day >= 21) || (month == 6 && day <= 20):
		return "♊ Близнецы"
	case (month == 6 && day >= 21) || (month == 7 && day <= 22):
		return "♋ Рак"
	case (month == 7 && day >= 23) || (month == 8 && day <= 22):
		return "♌ Лев"
	case (month == 8 && day >= 23) || (month == 9 && day <= 22):
		return "♍ Дева"
	case (month == 9 && day >= 23) || (month == 10 && day <= 22):
		return "♎ Весы"
	case (month == 10 && day >= 23) || (month == 11 && day <= 21):
		return "♏ Скорпион"
	case (month == 11 && day >= 22) || (month == 12 && day <= 21):
		return "♐ Стрелец"
	case (month == 12 && day >= 22) || (month == 1 && day <= 19):
		return "♑ Козерог"
	case (month == 1 && day >= 20) || (month == 2 && day <= 18):
		return "♒ Водолей"
	default:
		return "♓ Рыбы"
	}
}

// Расчёт возраста
func calculateAge(birth time.Time) int {
	now := time.Now()
	age := now.Year() - birth.Year()

	if now.YearDay() < birth.YearDay() {
		age--
	}

	return age
}

// ================== ГЛАВНОЕ МЕНЮ ==================

func main_menu(api *maxbot.Api, chatID int64, profile *UserState) (string, *maxbot.Keyboard) {

	// ===== Реальная статистика =====
	girlsReal, boysReal := getStats()

	// ===== Искусственные значения =====
	girlsFake := 412
	boysFake := 230

	girlsTotal := girlsFake + girlsReal
	boysTotal := boysFake + boysReal

	// Сброс WAL (чтобы база не пухла)
	// db.Exec("PRAGMA wal_checkpoint(TRUNCATE);")

	

	// Обновляем активность пользователя
	updateLastActivity(chatID)

	// ===== Расчёт онлайна =====
	rand.Seed(time.Now().UnixNano())
	onlineTotal := (girlsTotal + boysTotal)/2 + rand.Intn(31) - 15

	if onlineTotal < 1 {
		onlineTotal = 1
	} else if onlineTotal > girlsTotal+boysTotal {
		onlineTotal = girlsTotal + boysTotal
	}

	// ===== Текст =====
	headerText := fmt.Sprintf(
		"🔥 Онлайн прямо сейчас: %d человек\n👩 Девушек всего: %d\n👨 Парней всего: %d",
		onlineTotal, girlsTotal, boysTotal,
	)

	// ===== Эмодзи пользователя =====
	emoji := "👤"
	if profile != nil {
		switch profile.Gender {
		case "М":
			emoji = "👨"
		case "Ж":
			emoji = "👩"
		}
	}

	// ===== Клавиатура =====
	keyboard := api.Messages.NewKeyboardBuilder()

	keyboard.AddRow().AddCallback("🎲 Начать общение", schemes.DEFAULT, "ruletka")
	keyboard.AddRow().AddCallback("💎 VIP без ограничений", schemes.DEFAULT, "vip")
	keyboard.AddRow().AddCallback(fmt.Sprintf("%s Моя анкета", emoji), schemes.DEFAULT, "open_profile")
	keyboard.AddRow().AddCallback("🎯 Фильтры поиска", schemes.DEFAULT, "open_filters")
	keyboard.AddRow().AddCallback("📩 Пригласить друзей 🎁", schemes.DEFAULT, "invite")

	// Поддержка
	keyboard.AddRow().AddLink("🆘 Поддержка", schemes.DEFAULT, SUPPORT_URL)

	// Админка
	if chatID == ADMIN_ID {
		keyboard.AddRow().AddCallback("⚙ Админ панель", schemes.DEFAULT, "admin_panel")
	}

	return headerText, keyboard
}

// Отправка главного меню
func sendMainMenu(ctx context.Context, api *maxbot.Api, chatID int64) {

	// Загружаем профиль
	profile, err := loadProfileFromDB(fmt.Sprintf("%d", chatID))
	if err != nil {
		fmt.Println("Ошибка загрузки профиля:", err)
	}

	// Если нет профиля — создаём
	if profile == nil {
		fmt.Println("Профиль не найден, создаём новый")
		createProfile(chatID, "")

		profile, _ = loadProfileFromDB(fmt.Sprintf("%d", chatID))
		if profile == nil {
			msg := maxbot.NewMessage().
				SetChat(chatID).
				SetText("Добро пожаловать! Ваша анкета создаётся...")

			api.Messages.Send(ctx, msg)
			return
		}
	}

	// Обновляем кэш
	users[chatID] = profile

	// Генерируем меню
	text, keyboard := main_menu(api, chatID, profile)

	msg := maxbot.NewMessage().
		SetChat(chatID).
		SetText(text).
		AddKeyboard(keyboard)

	if err := api.Messages.Send(ctx, msg); err != nil {
		fmt.Println("Ошибка отправки меню:", err)
	}
}

// ================== КЛАВИАТУРЫ ==================

// После создания анкеты
func sendProfileActionMenu() *maxbot.Keyboard {
	kb := &maxbot.Keyboard{}
	kb.AddRow().
		AddCallback("💾 Сохранить ✅", schemes.DEFAULT, "save").
		AddCallback("✏️ Редактировать", schemes.DEFAULT, "edit_profile_after_creation").
		AddCallback("🗑 Удалить", schemes.DEFAULT, "delete_profile_now")
	return kb
}

// Меню существующей анкеты
func sendProfileMenu() *maxbot.Keyboard {
	kb := &maxbot.Keyboard{}
	kb.AddRow().
		AddCallback("✏️ Редактировать", schemes.DEFAULT, "edit_profile").
		AddCallback("🗑 Удалить", schemes.DEFAULT, "delete_profile").
		AddCallback("⬅️ Назад", schemes.DEFAULT, "back_to_menu")
	return kb
}

// ================== РЕДАКТИРОВАНИЕ ==================

// Выбор callback в зависимости от состояния
func chooseCallback(profilePayload, savePayload string, isSaved bool) string {
	if isSaved {
		return profilePayload
	}
	return savePayload
}

// Клавиатура редактирования
func getEditKeyboard(isSaved bool) *maxbot.Keyboard {
	kb := &maxbot.Keyboard{}

	kb.AddRow().
		AddCallback("📝 Имя", schemes.DEFAULT, chooseCallback("edit_name_profile", "edit_name_save", isSaved)).
		AddCallback("⚧ Пол", schemes.DEFAULT, chooseCallback("edit_gender_profile", "edit_gender_save", isSaved))

	kb.AddRow().
		AddCallback("🎂 Дата рождения", schemes.DEFAULT, chooseCallback("edit_birthdate_profile", "edit_birthdate_save", isSaved)).
		AddCallback("🏙 Город", schemes.DEFAULT, chooseCallback("edit_city_profile", "edit_city_save", isSaved))

	kb.AddRow().
		AddCallback("✍️ О себе", schemes.DEFAULT, chooseCallback("edit_about_profile", "edit_about_save", isSaved)).
		AddCallback("📸 Фото", schemes.DEFAULT, chooseCallback("edit_photo_profile", "edit_photo_save", isSaved))

	kb.AddRow().
		AddCallback(
			"👍 Готово",
			schemes.DEFAULT,
			map[bool]string{true: "edit_save_profile", false: "edit_done_create"}[isSaved],
		)

	return kb
}

// ================== ПОЛЬЗОВАТЕЛИ ==================

// Получить пользователя из кэша
func getUser(chatID int64) *UserState {
	u, ok := users[chatID]
	if !ok {
		u = &UserState{ChatID: chatID}
		users[chatID] = u
	}
	return u
}

// ================== УНИВЕРСАЛЬНАЯ ОТПРАВКА ==================

func sendMessage(ctx context.Context, api *maxbot.Api, chatID int64, text string, kb ...*maxbot.Keyboard) {
	msg := maxbot.NewMessage()
	msg.SetChat(chatID)
	msg.SetText(text)

	if len(kb) > 0 && kb[0] != nil {
		msg.AddKeyboard(kb[0])
	}

	api.Messages.Send(ctx, msg)
}

// ================== ВЫБОР ПОЛА ==================

// Клавиатура выбора пола
func genderKeyboard(api *maxbot.Api, chatID int64, prompt string) {
	kb := api.Messages.NewKeyboardBuilder()

	kb.AddRow().
		AddCallback("👨 Мужской", schemes.POSITIVE, "gender_m").
		AddCallback("👩 Женский", schemes.POSITIVE, "gender_f")

	msg := maxbot.NewMessage().
		SetChat(chatID).
		SetText(prompt).
		AddKeyboard(kb)

	api.Messages.Send(context.Background(), msg)
}

// Обработка выбора пола
func processGenderSelection(ctx context.Context, api *maxbot.Api, chatID int64, payload string) bool {
	state := users[chatID]
	if state == nil {
		return false
	}

	switch payload {
	case "gender_m":
		state.Gender = "М"
	case "gender_f":
		state.Gender = "Ж"
	case "gender_any":
		state.Gender = "Любой"
	default:
		return false
	}

	return true
}

// ================== ПРОЧЕЕ ==================

func saveMenu(ctx context.Context, api *maxbot.Api, chatID int64, state *UserState) {
	msg := maxbot.NewMessage().
		SetChat(chatID).
		SetText("Меню сохранения")

	api.Messages.Send(ctx, msg)
}



// ================= ПРИВЕТСТВИЕ =================

func sendWelcome(ctx context.Context, api *maxbot.Api, chatID int64) {
	msg := maxbot.NewMessage()
	msg.SetChat(chatID)

	photo, err := api.Uploads.UploadPhotoFromFile(ctx, "1.png")
	if err != nil {
		log.Println("Ошибка UploadPhotoFromFile:", err)
		return
	}
	msg.AddPhoto(photo)

	msg.SetText(`💕 Добро пожаловать в Чат-рулетку знакомств!

🎯 Что это?
Чат-рулетка знакомств — это бот для знакомств прямо в MAX.
Находи интересных людей из твоего города и начинай общаться при взаимных совпадениях по фильтру!

✨ Как это работает:
• Создай анкету с фото и описанием
• Заходишь, нажимаешь начать общение/найти собеседника
• Соединяешься с тем, кто подходит по твоим фильтрам, и общаешься

🚀 Начнём?
Нажми кнопку ниже, чтобы создать анкету!`)

	keyboard := api.Messages.NewKeyboardBuilder()
	keyboard.AddRow().
		AddCallback("Создать анкету", schemes.POSITIVE, "start_profile")

	msg.AddKeyboard(keyboard)

	api.Messages.Send(ctx, msg)
}






// ================= УНИВЕРСАЛЬНЫЙ ВЫБОР ГОРОДА =================
// ================= ГОРОДА =================

// sendCitySelection — показывает список городов по введённому тексту
func sendCitySelection(api *maxbot.Api, chatID int64, text string, limit int) {

    text = strings.TrimSpace(text)

    // Минимум 2 символа
    r := []rune(text)
    if len(r) < 2 {
        sendMessage(context.Background(), api, chatID, "Введите название города минимум 2 символа")
        return
    }

    // Проверка базы
    if geoDB == nil {
        sendMessage(context.Background(), api, chatID, "Ошибка базы городов")
        return
    }

    // Формируем поиск (первая буква заглавная)
    searchText := strings.ToUpper(string(r[0])) + strings.ToLower(string(r[1:])) + "%"

    rows, err := geoDB.Query(`
        SELECT TRIM(name), TRIM(region), TRIM(tz)
        FROM geo
        WHERE LOWER(name) LIKE ? COLLATE NOCASE
        ORDER BY name
        LIMIT ?
    `, searchText, limit)
    if err != nil {
        sendMessage(context.Background(), api, chatID, "Ошибка поиска города")
        return
    }
    defer rows.Close()

    // Локальная структура
    type City struct {
        Name, Region, Timezone string
    }

    var cities []City
    seen := map[string]bool{}

    // Читаем города и убираем дубликаты
    for rows.Next() {
        var name, region, timezone string
        if err := rows.Scan(&name, &region, &timezone); err != nil {
            continue
        }

        key := strings.ToLower(name) + "_" + strings.ToLower(region)
        if seen[key] {
            continue
        }
        seen[key] = true

        cities = append(cities, City{name, region, timezone})
    }

    // Если ничего не нашли
    if len(cities) == 0 {
        sendMessage(context.Background(), api, chatID, "Города не найдены")
        return
    }

    // ===== Клавиатура =====
    keyboard := api.Messages.NewKeyboardBuilder()

    for i, c := range cities {
        if i >= 5 {
            break
        }

        region := c.Region
        if region == "" {
            region = "-"
        }

        callback := fmt.Sprintf("city_%s_%s",
            strings.ReplaceAll(c.Name, " ", "_"),
            strings.ReplaceAll(region, " ", "_"),
        )

        keyboard.AddRow().AddCallback(
            fmt.Sprintf("%s (%s)", c.Name, region),
            schemes.DEFAULT,
            callback,
        )
    }

    // Отправка
    msg := maxbot.NewMessage()
    msg.SetChat(chatID)
    msg.SetText("Выберите город:")
    msg.AddKeyboard(keyboard)

    _ = api.Messages.Send(context.Background(), msg)
}


// processCitySelection — обработка выбора города
func processCitySelection(ctx context.Context, api *maxbot.Api, chatID int64, payload string, state *UserState) bool {

    // ===== Нажали кнопку города =====
    if strings.HasPrefix(payload, "city_") {

        parts := strings.SplitN(payload[len("city_"):], "_", 2)
        if len(parts) != 2 {
            return false
        }

        city := strings.ReplaceAll(parts[0], "_", " ")
        region := strings.ReplaceAll(parts[1], "_", " ")

        // Получаем таймзону
        var tz string
        row := geoDB.QueryRow(`SELECT tz FROM geo WHERE name = ? AND region = ?`, city, region)
        _ = row.Scan(&tz)

        // Сохраняем в state
        state.City = city
        state.Region = region
        state.Tz = tz

        return true
    }

    // ===== Ввели текст (поиск города) =====
    if strings.TrimSpace(payload) != "" {
        sendCitySelection(api, chatID, strings.TrimSpace(payload), 5)
        return false
    }

    return false
}

// ================== ОБРАБОТКА СОЗДАНИЯ / РЕДАКТИРОВАНИЯ ПРОФИЛЯ ==================
func processProfileCreationEdit(
    ctx context.Context,
    api *maxbot.Api,
    chatID int64,
    state *UserState,
    text string,
    attachments []interface{},
    payload string,
) bool {

    // Получаем или создаём пользователя
    user, ok := users[chatID]
    if !ok {
        user = &UserState{ChatID: chatID}
        users[chatID] = user
    }

    // ================== NAME ==================
    if state.Step == "waiting_name" ||
        state.Step == "edit_name_profile" ||
        state.Step == "edit_name_save" {

        state.Name = text

        if strings.HasPrefix(state.Step, "edit_") {
            saveProfileField(chatID, "name", state.Name)

            keyboard := getEditKeyboard(user.IsEditing)
            showProfile(ctx, api, chatID, state, keyboard)

        } else {
            state.Step = "gender_select"
            genderKeyboard(api, chatID, "Приятно познакомиться, "+state.Name+"\nВыберите ваш пол:")
            return true
        }

        state.Step = ""
        return true
    }

    // ================== GENDER ==================
    if state.Step == "gender_select" ||
        state.Step == "edit_gender_profile" ||
        state.Step == "edit_gender_save" {

        handled := processGenderSelection(ctx, api, chatID, payload)
        if !handled {
            return false
        }

        if strings.HasPrefix(state.Step, "edit_") {
            saveProfileField(chatID, "gender", state.Gender)

            keyboard := getEditKeyboard(user.IsEditing)
            showProfile(ctx, api, chatID, state, keyboard)

        } else {
            state.Step = "birth_day"
            sendMessage(ctx, api, chatID, "Введите день рождения (1-31):")
        }

        return true
    }

    // ================== BIRTHDATE ==================
    if state.Step == "birthdate_select" ||
        state.Step == "edit_birthdate_profile" ||
        state.Step == "edit_birthdate_save" ||
        state.Step == "birth_day" ||
        state.Step == "birth_month" ||
        state.Step == "birth_year" ||
        state.Step == "edit_birth_day" ||
        state.Step == "edit_birth_month" ||
        state.Step == "edit_birth_year" ||
        state.Step == "birth_done" ||
        state.Step == "edit_birth_done" {

        handleBirthdate(ctx, api, state, chatID, state.Step, text)

        // ===== После редактирования =====
        if state.Step == "edit_birth_done" {
            saveProfileField(chatID, "birthdate", state.Birthdate)
            saveProfileField(chatID, "age", state.Age)
            saveProfileField(chatID, "zodiac", state.Zodiac)

            keyboard := getEditKeyboard(user.IsEditing)
            showProfile(ctx, api, chatID, state, keyboard)

            state.Step = ""
            return true
        }

        // ===== После создания =====
        if state.Step == "birth_done" {
            state.Step = "waiting_city"
            state.anketa = false
            sendMessage(ctx, api, chatID, "Введите первые буквы города:")
            return true
        }

        return true
    }

    // ================== ГОРОД ==================

    // ===== Выбор города (кнопка) =====
    if strings.HasPrefix(payload, "city_") && payload != "city_filters" {

        handled := processCitySelection(ctx, api, chatID, payload, state)
        if !handled {
            sendMessage(ctx, api, chatID, "Город не найден, попробуйте ещё раз.")
            return true
        }

        // ===== ФИЛЬТР =====
        if state.Step == "filter_city" {
            db.Exec(
                "UPDATE profiles SET filters_city=?, filters_region=? WHERE user_id=?",
                state.City,
                state.Region,
                chatID,
            )

            state.Step = ""
            showFilters(ctx, api, chatID, state)
            return true
        }

        // ===== РЕДАКТИРОВАНИЕ АНКЕТЫ =====
        if state.anketa {
            saveProfileField(chatID, "city", state.City)
            saveProfileField(chatID, "region", state.Region)
            saveProfileField(chatID, "tz", state.Tz)

            keyboard := getEditKeyboard(user.IsEditing)
            showProfile(ctx, api, chatID, state, keyboard)
            return true
        }

        // ===== СОЗДАНИЕ =====
        state.Step = "waiting_about"
        sendMessage(ctx, api, chatID,
            fmt.Sprintf("🏙 Город выбран: %s (%s)\n\nРасскажите о себе:", state.City, state.Region),
        )

        return true
    }

    // ===== КНОПКИ ГОРОДА =====
    if payload == "edit_city_profile" || payload == "edit_city_save" {
        state.Step = "edit_city_profile"
        state.anketa = true
        sendMessage(ctx, api, chatID, "Введите название города:")
        return true
    }

    if payload == "city_filters" {
        state.Step = "filter_city"
        sendMessage(ctx, api, chatID, "Введите название города для фильтра:")
        return true
    }

    // ===== ВВОД ГОРОДА =====
    if state.Step == "waiting_city" ||
        state.Step == "edit_city_profile" ||
        state.Step == "filter_city" {

        sendCitySelection(api, chatID, strings.TrimSpace(text), 5)
        return true
    }

    // ================== ABOUT ==================
    if state.Step == "waiting_about" ||
        state.Step == "edit_about_profile" ||
        state.Step == "edit_about_save" ||
        state.Step == "edit_about" {

        state.About = text

        if strings.HasPrefix(state.Step, "edit_") {
            saveProfileField(chatID, "about", state.About)

            keyboard := getEditKeyboard(user.IsEditing)
            showProfile(ctx, api, chatID, state, keyboard)

        } else {
            state.Step = "waiting_photo"
            sendMessage(ctx, api, chatID, "📸 Прикрепите одно фото:")
        }

        return true
    }

    // ================== PHOTO ==================
    if state.Step == "waiting_photo" ||
        state.Step == "edit_photo_profile" ||
        state.Step == "edit_photo_save" ||
        state.Step == "edit_photo" {

        if len(attachments) == 0 {
            sendMessage(ctx, api, chatID, "📸 Пожалуйста отправьте фото", getEditKeyboard(user.IsEditing))
            return true
        }

        for _, a := range attachments {

            photo, ok := a.(*schemes.PhotoAttachment)
            if !ok {
                continue
            }

            token := photo.Payload.Token

            state.Photo = &schemes.PhotoTokens{
                Photos: map[string]schemes.PhotoToken{
                    "0": {Token: token},
                },
            }

            if strings.HasPrefix(state.Step, "edit_") {
                saveProfileField(chatID, "photo_url", token)

                keyboard := getEditKeyboard(user.IsEditing)
                showProfile(ctx, api, chatID, state, keyboard)

            } else {
                state.Step = "completed"

                saveProfile(chatID, stateToMap(state))

                keyboard := sendProfileActionMenu()
                showProfile(ctx, api, chatID, state, keyboard)
            }
        }

        return true
    }

    return false
}


// обработка ввода нового значения таймера
///// Установка таймера
func HandleAdminTimerInput(api *maxbot.Api, chatID int64, text string) {

	state, ok := users[chatID]
	if !ok || state.Step != "waiting_timer" {
		return
	}

	seconds, err := strconv.Atoi(text)
	if err != nil || seconds < 10 || seconds > 3600 {
		msg := maxbot.NewMessage().
			SetChat(chatID).
			SetText("⛔ Таймер должен быть от 10 до 3600 секунд. Попробуйте ещё раз.")

		err := api.Messages.Send(context.Background(), msg)
		if err != nil {
			fmt.Println("SEND ERROR:", err)
		}
		return
	}

	SetChatTimer(seconds)

	msg := maxbot.NewMessage().
		SetChat(chatID).
		SetText(fmt.Sprintf("✅ Таймер успешно обновлён: %d секунд", seconds))

	err = api.Messages.Send(context.Background(), msg)
	if err != nil {
		fmt.Println("SEND ERROR:", err)
	}

	ShowAdminPanel(api, chatID)

	// сбрасываем состояние
	state.Step = ""
}






///////////=================Профиль
func showProfile(ctx context.Context, api *maxbot.Api, chatID int64, state *UserState, keyboard *maxbot.Keyboard) {
    
    //updateLastActivity(chatID)
	//db.Exec("PRAGMA wal_checkpoint(FULL);")
	
	msg := maxbot.NewMessage()
    msg.SetChat(chatID)

    if state.Photo != nil {
        msg.AddPhoto(state.Photo)
    }

    vip := "Нет"
    if state.IsVIP {
        vip = "Да"
    }

    emoji := "👤"
    switch state.Gender {
    case "Мужской", "М":
        emoji = "👨"
    case "Женский", "Ж":
        emoji = "👩"
    }

    msg.SetText(fmt.Sprintf(
        "%s Анкета\n"+
		"Имя: %s\n"+
		"Пол: %s\n"+
		"🎂 Дата рождения: %02d.%02d.%04d\n"+
		"🎈 Возраст: %d\n"+
		"🪐 Знак зодиака: %s\n"+
		"🏙 Город: %s\n"+
		"✍️ О себе: %s\n"+
		"💎 VIP: %s",
        emoji,
        state.Name,
        state.Gender,
        state.BirthDay,
        state.BirthMonth,
        state.BirthYear,
        state.Age,
        state.Zodiac,
        state.City,
        state.About,
        vip,
    ))

    if keyboard != nil {
        msg.AddKeyboard(keyboard)
    }

    if err := api.Messages.Send(ctx, msg); err != nil {
        log.Println("Ошибка отправки профиля:", err)
    }
}



// ==================== Стартовая логика ====================

func commonStartHandler(ctx context.Context, api *maxbot.Api, chatID int64, payload string) {
    if payload != "" && payload == fmt.Sprint(chatID) {
        payload = ""
    }

    //log.Printf("BOT_STARTED: chat_id=%d, payload=%s\n", chatID, payload)

    if _, ok := users[chatID]; !ok {
        users[chatID] = &UserState{Step: ""}
    }

    // получаем профиль из базы (chatID преобразуем в string)
    profile, err := loadProfileFromDB(fmt.Sprintf("%d", chatID))
    if err != nil {
        log.Println("Ошибка загрузки профиля:", err)
    }

    if profile == nil {
        log.Println("Профиля нет, создаём новый")

        invitedBy := ""
        if payload != "" {
            invitedBy = payload
            log.Printf("Реферал от %s\n", invitedBy)
        }

        err := createProfile(chatID, invitedBy)
        if err != nil {
            log.Println("Ошибка создания профиля:", err)
        }

        if invitedBy != "" {
            err := processReferral(invitedBy, chatID)
            if err != nil {
                log.Println("Ошибка реферала:", err)
            }
        }

        // повторная загрузка
        profile, err = loadProfileFromDB(fmt.Sprintf("%d", chatID))
        if err != nil || profile == nil {
            log.Println("КРИТИЧНО: профиль не загрузился после создания")
            sendWelcome(ctx, api, chatID)
            return
        }
    }

    // защита от nil
    if profile == nil {
        sendWelcome(ctx, api, chatID)
        return
    }

    // профиль помечен на удаление
    if profile.DeletedAt != 0 {
        msg := maxbot.NewMessage().
            SetChat(chatID).
            SetText("⚠️ Ваша анкета помечена на удаление. Восстановить?")

        keyboard := api.Messages.NewKeyboardBuilder()
        keyboard.AddRow().
            AddCallback("✅ Да", schemes.POSITIVE, "restore_profile").
            AddCallback("❌ Нет", schemes.DEFAULT, "main_menu")

        msg.AddKeyboard(keyboard)
        api.Messages.Send(ctx, msg)
        return
    }

    // если профиль есть — показываем главное меню
    sendMainMenu(ctx, api, chatID)
}



///////////////Функция кнопки начать
func tryOpenMainMenu(ctx context.Context, api *maxbot.Api, chatID int64) bool {
    state, ok := users[chatID]
    if !ok || state == nil {
        state = &UserState{ChatID: chatID}
        users[chatID] = state
    }

    // если нет данных — грузим из базы
    if state.Name == "" || state.Name == "—" {
        dbState, err := loadProfileFromDB(fmt.Sprintf("%d", chatID))
        if err == nil && dbState != nil {
            state = dbState
            users[chatID] = state
            fmt.Println("[INFO] Профиль загружен из базы:", chatID)
        }
    }

    // если анкета есть → открываем меню
    if state.Name != "" && state.Name != "—" {
        fmt.Println("[INFO] Открываем main_menu для:", chatID)

        text, keyboard := main_menu(api, chatID, state)

        msg := maxbot.NewMessage().
            SetChat(chatID).
            SetText(text).
            AddKeyboard(keyboard)

        if err := api.Messages.Send(ctx, msg); err != nil {
            fmt.Println("Ошибка отправки main_menu:", err)
        }

        return true
    }

    return false
}






func main() {
    // ================= Инициализация =================
    initDB()
    startAutoDelete()

    token := "f9LHodD0cOJifvwS05WVOZ0E3rbxxlLRTt5JcHdB2ezESF1dp1N4jaNe9S5_UeZYXBcqF9KC5H8JfaUDfpeg"
    if token == "" {
        panic("BOT_TOKEN не установлен")
    }

    api, err := maxbot.New(token)
    if err != nil {
        panic(err)
    }

    // Запуск фоновых процессов
    go pollPaymentsYooKassa(api)
    go startActivityUpdater() // проверка онлайн

    ctx, cancel := context.WithCancel(context.Background())

    // Graceful shutdown
    go func() {
        stop := make(chan os.Signal, 1)
        signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
        <-stop
        fmt.Println("Остановка бота...")
        cancel()
    }()

    fmt.Println("🚀 Запуск MAX бота (Long Polling)...")

    // ================= Long Polling =================
    for upd := range api.GetUpdates(ctx) {
        switch u := upd.(type) {

        // ---- Старт бота ----
        case *schemes.BotStartedUpdate:
            chatID := u.ChatId
            payload := u.Payload // реферал

            //fmt.Println("[EVENT] bot_started:", chatID, "payload:", payload)
            commonStartHandler(ctx, api, chatID, payload)

       









	   // ---- Сообщение от пользователя ----
case *schemes.MessageCreatedUpdate:



//Рулетка общение
chatID := u.Message.Recipient.ChatId
state, ok := users[chatID]
if !ok {
    state = &UserState{}
    users[chatID] = state
}
text := u.Message.Body.Text


mu.Lock()
partnerID, inChat := activeChats[chatID]
mu.Unlock()

// ===== ЕСЛИ В ЧАТЕ → ПЕРЕСЫЛКА =====
if inChat {

    msg := maxbot.NewMessage().SetChat(partnerID)

    if text != "" {
        msg.SetText(text)
    }

    // ===== ПРОВЕРКА VIP НА ВЛОЖЕНИЯ =====
    hasAttachments := len(u.Message.Body.Attachments) > 0

    user := users[chatID]

    if hasAttachments && (user == nil || !user.IsVIP) {

        vipMsg := maxbot.NewMessage().
            SetChat(chatID).
            SetText("🚫 Отправка файлов доступна только для VIP.\n\n💎 Подключите VIP, чтобы отправлять фото, видео и документы.")

        kb := api.Messages.NewKeyboardBuilder()
        kb.AddRow().AddCallback("💎 Подключить VIP", schemes.DEFAULT, "vip")

        vipMsg.AddKeyboard(kb)

        _ = api.Messages.Send(ctx, vipMsg)

        continue // ❗ блокируем отправку дальше
    }

    // ===== ВЛОЖЕНИЯ (только для VIP) =====
    for _, att := range u.Message.Body.Attachments {

        switch a := att.(type) {

        case *schemes.PhotoAttachment:
            msg.AddPhotoByToken(a.Payload.Token)

        case *schemes.AudioAttachment:
            msg.AddAudio(&schemes.UploadedInfo{
                Token: a.Payload.Token,
            })

        case *schemes.VideoAttachment:
            msg.AddVideo(&schemes.UploadedInfo{
                Token: a.Payload.Token,
            })

        case *schemes.FileAttachment:
            msg.AddFile(&schemes.UploadedInfo{
                Token: a.Payload.Token,
            })
        }
    }

    err := api.Messages.Send(ctx, msg)
    if err != nil {
        fmt.Println("[FORWARD ERROR]", err)
    }

    continue
}
	
	
	
	
	
	
	
	
	
	
	
	
















            // ===== ОБРАБОТКА /start =====
            if strings.HasPrefix(text, "/start") {
                fmt.Println("[EVENT] /start received:", chatID)
                payload := ""
                parts := strings.Split(text, " ")
                if len(parts) > 1 {
                    payload = parts[1]
                }
                commonStartHandler(ctx, api, chatID, payload)
                continue
            }

            // Вложения
            var userAttachments []interface{}
            for _, a := range u.Message.Body.Attachments {
                userAttachments = append(userAttachments, a)
            }

            // Защита от пустых сообщений
            if text == "" && len(userAttachments) == 0 {
                continue
            }

            // ==== Обработка даты рождения ====
            if state.Step == "birth_day" || state.Step == "birth_month" || state.Step == "birth_year" ||
                state.Step == "edit_birth_day" || state.Step == "edit_birth_month" || state.Step == "edit_birth_year" {
                handleBirthdate(ctx, api, state, chatID, state.Step, text)
                continue
            }

            // ==== Редактирование / создание профиля ====
            if state.Step == "filter_city" {
                sendCitySelection(api, chatID, text, 5)
                continue
            }

            if state.Step != "" {
                handled := processProfileCreationEdit(ctx, api, chatID, state, text, u.Message.Body.Attachments, "")
                if handled {
                    continue
                }
            }

            // ==== Спец. ввод для админа (например таймер) ====
            if text != "" {
                if state, ok := users[chatID]; ok && state.Step == "waiting_timer" {
                    HandleAdminTimerInput(api, chatID, text)
                    continue
                }
            }

        // ---- Колбек кнопки ----
        case *schemes.MessageCallbackUpdate:
            chatID := u.Message.Recipient.ChatId
            payload := u.Callback.Payload

            //fmt.Println("[CALLBACK] chatID:", chatID, "payload:", payload)

            // Проверяем существование state
            state, ok := users[chatID]
            if !ok || state == nil {
                state = &UserState{ChatID: chatID}
                users[chatID] = state
            }
































///////////========Колбеки Рулетка


if payload == "ruletka" {
    // Создаём клавиатуру
    keyboard := api.Messages.NewKeyboardBuilder()

    // 1-я строка: Найти собеседника
    keyboard.AddRow().AddCallback("▶ Найти собеседника", schemes.POSITIVE, "roulette_in")

    // 2-я строка: Выйти из чата
    keyboard.AddRow().AddCallback("⏹ Выйти из чата", schemes.NEGATIVE, "roulette_out")

    // Создаём сообщение
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText("💬 Чат-рулетка готова. Выберите действие:").
        AddKeyboard(keyboard)

    // Отправляем
    err := api.Messages.Send(context.Background(), msg)
    if err != nil {
        fmt.Println("Ошибка отправки сообщения рулетки:", err)
    }
}


/*if payload == "roulette_in" {
    //fmt.Println("[CALLBACK] roulette_in:", chatID)
    go autoConnectUsers(ctx, api, chatID, 268107644) // подключаем тестовую барышню
}*/


if payload == "roulette_in" {
    //fmt.Println("[CALLBACK] roulette_in:", chatID)
    go rouletteIn(ctx, api, chatID)
}

if payload == "roulette_out" {
    //fmt.Println("[CALLBACK] roulette_out:", chatID)
    go rouletteOut(ctx, api, chatID)
}





























///////////========Колбеки ВИП
if payload == "vip" {
    profile := getProfile(chatID)
    if profile == nil {
        msg := maxbot.NewMessage().
            SetChat(chatID).
            SetText("❗ Профиль не найден.")
        api.Messages.Send(context.Background(), msg)
        continue
    }

    // Проверяем VIP
    vipUntilStr, _ := profile["vip_until"].(string)
    vipActive := false

    if vipUntilStr != "" && vipUntilStr != "—" {
        vipUntil, err := time.Parse("2006-01-02 15:04:05", vipUntilStr)
        if err == nil && time.Now().Before(vipUntil) {
            vipActive = true
        }
    }

    if vipActive {
        text := fmt.Sprintf("💎 VIP уже активен!\n\n📅 Действует до: %s\n\nВы можете продлить подписку:", vipUntilStr)
        kb := api.Messages.NewKeyboardBuilder()
        kb.AddRow().AddCallback("🔁 Продлить VIP", schemes.DEFAULT, "vip_tariv")
        kb.AddRow().AddCallback("⬅ Назад", schemes.DEFAULT, "main_menu")

        api.Messages.Send(context.Background(),
            maxbot.NewMessage().SetChat(chatID).SetText(text).AddKeyboard(kb),
        )
    } else {
        text := VIP_TEXT // твой текст оферты
        kb := api.Messages.NewKeyboardBuilder()
        kb.AddRow().AddCallback("📄 Условия оферты", schemes.DEFAULT, "show_offer")
        kb.AddRow().AddCallback("💎 Оформить VIP", schemes.DEFAULT, "vip_tariv")
        kb.AddRow().AddCallback("⬅ Назад", schemes.DEFAULT, "main_menu")

        api.Messages.Send(context.Background(),
            maxbot.NewMessage().SetChat(chatID).SetText(text).AddKeyboard(kb),
        )
    }

    continue
}

if payload == "vip_tariv" {
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText("💎 Выберите тариф:👇").
        AddKeyboard(vip_keyboard()) // <- вызываем функцию

    api.Messages.Send(context.Background(), msg)
    continue
}

if payload == "show_offer" {
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText(OFFER_TEXT). // OFFER_TEXT нужно объявить как const или var
        AddKeyboard(vip_offer_keyboard()) // функция возвращает *maxbot.Keyboard
    api.Messages.Send(context.Background(), msg)
    continue
}

if payload == "offer_accept" {
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText("💎 Выбирайте тариф для подписки").
        AddKeyboard(vip_keyboard())
    api.Messages.Send(context.Background(), msg)
    continue
}

if payload == "offer_decline" {
    state, ok := users[chatID]
    if !ok || state == nil {
        state = &UserState{ChatID: chatID}
        users[chatID] = state
    }

    text, keyboard := main_menu(api, chatID, state)

    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText(fmt.Sprintf(
            "❌ Вы не приняли условия оферты.\n\nVIP-функции недоступны.\n\n%s",
            text,
        )).
        AddKeyboard(keyboard)

    api.Messages.Send(context.Background(), msg)
    continue
}

if tariff, ok := TARIFFS[payload]; ok {
    amount := tariff.Price
    description := tariff.Name
    days := tariff.Days

    payment, err := createPayment(amount, description, chatID, days)
    if err != nil {
        api.Messages.Send(context.Background(),
            maxbot.NewMessage().SetChat(chatID).SetText("❌ Ошибка создания платежа."))
        continue
    }

    paymentURL := payment.Confirmation.ConfirmationURL

    if paymentURL == "" {
        fmt.Println("[VIP] ❌ пустой payment URL")
        continue
    }

    // ✅ ВАЖНО: без лишнего аргумента
    saveOrder(payment.ID, chatID, days)

    kb := PayKeyboard(paymentURL)

    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText("💎 Перейдите к оплате").
        AddKeyboard(kb)

    api.Messages.Send(context.Background(), msg)
    continue
}


///////////========Колбеки админ панель

// Открытие панели админа
if payload == "admin_panel" {
    ShowAdminPanel(api, chatID) // Показываем админку
    continue
}

// ==== Обработка колбека изменения таймера ====
if payload == "admin_timer" {
    current := GetChatTimer()
    text := fmt.Sprintf("⏳ Текущий таймер: %d сек.\nВведите новое значение:", current)

    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText(text)

    if err := api.Messages.Send(context.Background(), msg); err != nil {
        fmt.Println("SEND ERROR:", err)
    }

    state.Step = "waiting_timer" // ждем ввода нового таймера
    continue
}

// ==== Включение VIP через админку ====
if payload == "admin_vip_on" {
    vipUntil := activateVIP(chatID, 3650) // даем VIP на 10 лет
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText(fmt.Sprintf("✅ VIP включён\nДо %s", vipUntil))
    api.Messages.Send(context.Background(), msg)

    ShowAdminPanel(api, chatID) // показываем админку заново
    continue
}

// ==== Выключение VIP через админку ====
if payload == "admin_vip_off" {
    deactivateVIP(chatID)
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText("❌ VIP отключён")
    api.Messages.Send(context.Background(), msg)

    ShowAdminPanel(api, chatID) // показываем админку заново
    continue
}

// ==== Обновление данных / перерисовка админки ====
if payload == "admin_refresh" {
    ShowAdminPanel(api, chatID)
    continue
}












// ========================
// ======== Фильтры =======
// ========================

if payload == "open_filters" {
    showFilters(ctx, api, chatID, state)
    continue
}

if payload == "gender_filters" {
    state.Step = "filter_genders"

    kb := api.Messages.NewKeyboardBuilder()
    kb.AddRow().AddCallback("👨 Парни", schemes.DEFAULT, "gender_filter_m")
    kb.AddRow().AddCallback("👩 Девушки", schemes.DEFAULT, "gender_filter_f")
    kb.AddRow().AddCallback("🎭 Любой", schemes.DEFAULT, "gender_filter_any")

    api.Messages.Send(ctx, maxbot.NewMessage().
        SetChat(chatID).
        SetText("Выберите пол").
        AddKeyboard(kb),
    )
    continue
}

if payload == "gender_filter_m" || payload == "gender_filter_f" || payload == "gender_filter_any" {
    var gender string
    switch payload {
    case "gender_filter_m":
        gender = "М"
    case "gender_filter_f":
        gender = "Ж"
    case "gender_filter_any":
        gender = "Любой"
    }

    state.Gender = gender
    UpdateFilter(chatID, "filters_gender", gender)
    showFilters(ctx, api, chatID, state)
    continue
}

if payload == "age_filters" {
    state.Step = "age_filters"

    row := db.QueryRow("SELECT filters_age_min, filters_age_max FROM profiles WHERE user_id = ?", chatID)
    var minAge, maxAge sql.NullInt64
    if err := row.Scan(&minAge, &maxAge); err == nil {
        if minAge.Valid {
            state.FilterAgeMin = int(minAge.Int64)
        } else {
            state.FilterAgeMin = 18
        }

        if maxAge.Valid {
            state.FilterAgeMax = int(maxAge.Int64)
        } else {
            state.FilterAgeMax = 35
        }
    }

    sendAgeKeyboard(ctx, api, chatID, state.FilterAgeMin, state.FilterAgeMax)
    continue
}

if strings.HasPrefix(payload, "age_") {
    updated := false

    switch payload {
    case "age_min_minus":
        if state.FilterAgeMin > 18 {
            state.FilterAgeMin--
            UpdateFilter(chatID, "filters_age_min", state.FilterAgeMin)
            updated = true
        }
    case "age_min_plus":
        if state.FilterAgeMin < state.FilterAgeMax {
            state.FilterAgeMin++
            UpdateFilter(chatID, "filters_age_min", state.FilterAgeMin)
            updated = true
        }
    case "age_max_minus":
        if state.FilterAgeMax > state.FilterAgeMin {
            state.FilterAgeMax--
            UpdateFilter(chatID, "filters_age_max", state.FilterAgeMax)
            updated = true
        }
    case "age_max_plus":
        if state.FilterAgeMax < 100 {
            state.FilterAgeMax++
            UpdateFilter(chatID, "filters_age_max", state.FilterAgeMax)
            updated = true
        }
    case "done_filters":
        state.Step = "filters"
        showFilters(ctx, api, chatID, state)
        continue
    }

    if updated {
        sendAgeKeyboard(ctx, api, chatID, state.FilterAgeMin, state.FilterAgeMax)
    }
    continue
}

if payload == "done_filters" {
    showFilters(ctx, api, chatID, state)
    continue
}

if payload == "filters_reset" {
    ResetFilters(chatID)
    showFilters(ctx, api, chatID, state)
    continue
}

if payload == "city_filters" {
    state.Step = "filter_city"

    sendMessage(ctx, api, chatID,
        "Введите название города для фильтра:",
        nil,
    )
    continue
}






// ====================== УДАЛЕНИЕ ПРОФИЛЯ ======================

if payload == "delete_profile_now" {
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText("⚠️ Вы уверены, что хотите удалить профиль?")

    kb := api.Messages.NewKeyboardBuilder()
    kb.AddRow().
        AddCallback("✅ Да", schemes.POSITIVE, "confirm_delete").
        AddCallback("❌ Нет", schemes.DEFAULT, "cancel_delete")

    msg.AddKeyboard(kb)
    api.Messages.Send(ctx, msg)
    continue
}

if payload == "confirm_delete" {
    deleteProfile(chatID)        // удаляем профиль из БД
    delete(users, chatID)        // очищаем состояние пользователя
    sendWelcome(ctx, api, chatID) // стартуем с приветствия
    continue
}

if payload == "cancel_delete" {
    state = users[chatID]

    // если state nil — подгружаем из базы
    if state == nil {
        dbState, err := loadProfileFromDB(fmt.Sprintf("%d", chatID))
        if err != nil {
            sendWelcome(ctx, api, chatID)
            continue
        }
        state = dbState
        users[chatID] = state
    }

    // показываем профиль с обновлённой клавиатурой
    keyboard := sendProfileActionMenu() // <- заменили на функцию
    showProfile(ctx, api, chatID, state, keyboard)
    continue
}


// ==================== Удаление и восстановление анкеты ====================

if payload == "delete_profile" {
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText("Анкета будет удалена через 30 дней.\n\nВы уверены, что хотите удалить анкету?")

    kb := api.Messages.NewKeyboardBuilder()
    kb.AddRow().
        AddCallback("✅ Да", schemes.DEFAULT, "confirm_delete_profile").
        AddCallback("❌ Нет", schemes.DEFAULT, "cancel_delete_profile")

    msg.AddKeyboard(kb)
    api.Messages.Send(ctx, msg)
    continue
}

if payload == "cancel_delete_profile" {
    state = users[chatID]

    if state == nil {
        s, err := loadProfileFromDB(fmt.Sprintf("%d", chatID))
        if err == nil {
            state = s
            users[chatID] = state
        }
    }

    if state != nil {
        keyboard := sendProfileMenu() // <- аккуратная функция для клавиатуры
        showProfile(ctx, api, chatID, state, keyboard)
    }
    continue
}

if payload == "confirm_delete_profile" {
    state = users[chatID]
    if state != nil {
        state.DeletedAt = time.Now().Add(30 * 24 * time.Hour).Unix()
        updateProfileDeletedAt(chatID, state.DeletedAt)

        msg := maxbot.NewMessage().
            SetChat(chatID).
            SetText("⚠ Ваша анкета будет удалена через 30 дней.\n\nХотите восстановить её?")

        kb := api.Messages.NewKeyboardBuilder()
        kb.AddRow().
            AddCallback("♻ Восстановить", schemes.POSITIVE, "restore_profile").
            AddCallback("❌ Нет", schemes.DEFAULT, "cancel_restore")

        msg.AddKeyboard(kb)
        api.Messages.Send(ctx, msg)
    }
    continue
}

if payload == "restore_profile" {
    state = users[chatID]
    if state == nil {
        s, err := loadProfileFromDB(fmt.Sprintf("%d", chatID))
        if err == nil {
            state = s
            users[chatID] = state
        }
    }

    if state != nil && state.DeletedAt > 0 {
        state.DeletedAt = 0
        users[chatID] = state

        conn, err := sql.Open("sqlite3", DB_FILE)
        if err == nil {
            stmt, err := conn.Prepare("UPDATE profiles SET deleted_at=? WHERE user_id=?")
            if err == nil {
                stmt.Exec(nil, chatID)
                stmt.Close()
            }
            conn.Close()
        }

        sendMainMenu(ctx, api, chatID)
    }
    continue
}

if payload == "cancel_restore" {
    state = users[chatID]
    if state == nil {
        s, err := loadProfileFromDB(fmt.Sprintf("%d", chatID))
        if err == nil {
            state = s
            users[chatID] = state
        }
    }

    if state != nil && state.DeletedAt > 0 {
        msg := maxbot.NewMessage().
            SetChat(chatID).
            SetText(formatDeleteCountdown(state.DeletedAt, state.Tz))

        kb := api.Messages.NewKeyboardBuilder()
        kb.AddRow().
            AddCallback("♻ Восстановить", schemes.POSITIVE, "restore_profile")

        msg.AddKeyboard(kb)
        api.Messages.Send(ctx, msg)
    }
    continue
}




// ================== CALLBACK ОБРАБОТКА ==================

// ---- Начало создания анкеты ----
if payload == "start_profile" {
    users[chatID] = &UserState{
        Step: "waiting_name",
    }
    sendMessage(ctx, api, chatID, "Давай создадим анкету.\nКак тебя зовут?", nil)
    continue
}

// ================== КОЛБЕКИ РЕДАКТИРОВАНИЯ ==================

// ---- Имя ----
if payload == "edit_name_profile" || payload == "edit_name_save" || payload == "waiting_name" {
    state = users[chatID]
    state.Step = payload
    sendMessage(ctx, api, chatID, "Введите имя:", nil)
    continue
}

// ---- Пол ----
if payload == "edit_gender_save" || payload == "edit_gender_profile" || payload == "waiting_gender" {
    state = users[chatID]
    state.Step = "edit_gender_profile"
    genderKeyboard(api, chatID, "Выберите пол:")
    continue
}

if (payload == "gender_m" || payload == "gender_f") && state.Step != "filter_gender" {
    if !processProfileCreationEdit(ctx, api, chatID, state, "", nil, payload) {
        continue
    }
    continue
}

// ---- Дата рождения ----
if payload == "edit_birthdate_profile" || payload == "edit_birthdate_save" {
    state = users[chatID]
    state.Step = "edit_birth_day"
    sendMessage(ctx, api, chatID, "Введите день рождения (1-31):", nil)
    continue
}

if payload == "waiting_birthdate" {
    state = users[chatID]
    state.Step = "birth_day"
    sendMessage(ctx, api, chatID, "Введите день рождения (1-31):", nil)
    continue
}

// ---- Город ----
if payload == "edit_city_save" || payload == "edit_city_profile" {
    state = users[chatID]
    state.Step = "edit_city_profile"
    processProfileCreationEdit(ctx, api, chatID, state, "", nil, payload)
    continue
}

if strings.HasPrefix(payload, "city_") {
    state = users[chatID]
    processProfileCreationEdit(ctx, api, chatID, state, "", nil, payload)
    continue
}

// ---- О себе ----
if payload == "edit_about_save" || payload == "edit_about_profile" || payload == "waiting_about" {
    u, ok := users[chatID]
    if !ok {
        u = &UserState{ChatID: chatID}
        users[chatID] = u
    }

    u.Step = "edit_about"
    u.IsEditing = strings.HasSuffix(payload, "_save") || strings.HasSuffix(payload, "_profile")
    u.EditingExisting = strings.HasSuffix(payload, "_profile")

    sendMessage(ctx, api, chatID, "Напишите о себе:", nil)
    continue
}

// ---- Фото ----
if payload == "edit_photo_save" || payload == "edit_photo_profile" {
    state = users[chatID]
    state.Step = "edit_photo"
    sendMessage(ctx, api, chatID, "Отправьте новое фото:", nil)
    continue
}            
			
// ================== Открытие меню редактирования ==================
if payload == "edit_profile" || payload == "edit_profile_after_creation" {
    u, ok := users[chatID]
    if !ok {
        u = &UserState{
            ChatID: chatID,
        }
        users[chatID] = u
    }

    u.Step = "edit_menu"

    // Особенность: IsEditing определяет тип клавиатуры
    if payload == "edit_profile" {
        u.IsEditing = false
    } else {
        u.IsEditing = true
    }

    keyboard := getEditKeyboard(u.IsEditing)
    sendMessage(ctx, api, chatID, "Что вы хотите изменить?", keyboard)
    continue
}

// ================== Кнопки "Готово" ==================

// ---- Готово 2 ----
if payload == "edit_done_create" {
    state.Step = ""
    keyboard := sendProfileMenu()
    showProfile(ctx, api, chatID, state, keyboard)
    continue
}

// ---- Готово 1 ----
if payload == "edit_save_profile" {
    state.Step = ""
    keyboard := sendProfileActionMenu()
    showProfile(ctx, api, chatID, state, keyboard)
    continue
}

// ================== СОХРАНИТЬ АНКЕТУ ==================
if payload == "save" {
    text, keyboard := inviteMessage(chatID)
    msg := maxbot.NewMessage()
    msg.SetChat(chatID)
    msg.SetText(text)
    msg.AddKeyboard(keyboard)
    api.Messages.Send(ctx, msg)
    continue
}

// ================== Пригласить друзей ==================
if payload == "invite" {
    text, keyboard := inviteMessage(chatID)
    msg := maxbot.NewMessage()
    msg.SetChat(chatID)
    msg.SetText(text)
    msg.AddKeyboard(keyboard)
    api.Messages.Send(ctx, msg)
    continue
}

// ================== Открыть анкету ==================
if payload == "open_profile" {
    state, err := loadProfileFromDB(fmt.Sprintf("%d", chatID))
    if err != nil || state == nil {
        msg := maxbot.NewMessage()
        msg.SetChat(chatID)
        msg.SetText("⚠️ Профиль не найден")
        api.Messages.Send(ctx, msg)
        continue
    }

    // Сохраняем state в память
    users[chatID] = state

    // Используем меню профиля
    keyboard := sendProfileMenu()
    showProfile(ctx, api, chatID, state, keyboard)
    continue
}

// ================== Вернуться в главное меню ==================
if payload == "back_to_menu" || payload == "main_menu" {
    sendMainMenu(ctx, api, chatID)
    continue






}}}}




// ================= БАЗА ДАННЫХ =================
func initDB() {
    var err error
    db, err = sql.Open("sqlite3", DB_FILE)
    if err != nil {
        log.Fatal("Ошибка открытия базы:", err)
    }

    // Проверка соединения
    if err = db.Ping(); err != nil {
        log.Fatal("Ошибка соединения с базой:", err)
    }

    log.Println("Инициализация таблиц...")

    // ПРОФИЛИ
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS profiles (
        user_id TEXT PRIMARY KEY,
        name TEXT,
        gender TEXT,
        birthdate TEXT,
        age INTEGER,
        zodiac TEXT,
        city TEXT,
        region TEXT,
        tz TEXT DEFAULT 'UTC',
        about TEXT,
        photo_url TEXT,
        is_vip INTEGER DEFAULT 0,
        vip_until TEXT DEFAULT NULL,
        deleted_at INTEGER DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        filters_gender TEXT DEFAULT 'Любой',
        filters_age_min INTEGER DEFAULT 18,
        filters_age_max INTEGER DEFAULT 35,
        filters_city TEXT DEFAULT 'Любой',
        filters_region TEXT DEFAULT 'Любой',
        is_subscribed INTEGER DEFAULT 0,
        subscription_expire TEXT DEFAULT NULL,
        invited_by TEXT DEFAULT NULL,
        invites INTEGER DEFAULT 0,
        last_activity INTEGER DEFAULT 0
    );`)
    if err != nil {
        log.Fatal("Ошибка создания таблицы profiles:", err)
    }

    // ACTIVE CHATS
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS active_chats (
        user1 TEXT,
        user2 TEXT,
        started_at INTEGER DEFAULT (strftime('%s','now'))
    );`)
    if err != nil {
        log.Fatal("Ошибка создания таблицы active_chats:", err)
    }

    // PAYMENTS
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        chat_id INTEGER,
        payment_id TEXT,
        days INTEGER,
        price INTEGER,
        status TEXT
    );`)
    if err != nil {
        log.Fatal("Ошибка создания таблицы payments:", err)
    }

    // РУЛЕТКА
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS roulette_queue (
        user_id TEXT PRIMARY KEY,
        joined_at INTEGER
    );`)
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS roulette_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,
        user_id TEXT,
        event TEXT,
        partner_id TEXT
    );`)
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS roulette_filters (
        user_id TEXT PRIMARY KEY,
        gender TEXT DEFAULT NULL,
        min_age INTEGER DEFAULT NULL,
        max_age INTEGER DEFAULT NULL,
        city TEXT DEFAULT NULL
    );`)

    // ИСТОРИЯ ПОИСКА
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        searched_at INTEGER DEFAULT (strftime('%s','now'))
    );`)

    // ИСТОРИЯ МАТЧЕЙ
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS match_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user1_id TEXT,
        user2_id TEXT,
        matched_at INTEGER DEFAULT (strftime('%s','now'))
    );`)

    // НАСТРОЙКИ БОТА
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );`)
    _, err = db.Exec(`
    INSERT OR IGNORE INTO bot_settings (key,value)
    VALUES ('chat_timer','180');`)

    // РЕФЕРАЛЫ
    _, err = db.Exec(`
    CREATE TABLE IF NOT EXISTS referrals (
        inviter_id TEXT,
        invited_id TEXT UNIQUE
    );`)

    log.Println("База данных готова")
}




// ================== Работа с базой профиля ==================

// Сохраняет профиль в базу
func saveProfile(userID int64, newData map[string]interface{}) error {
    // Получаем текущий профиль
    profile := getProfile(userID)

    // Обновляем поля из newData
    for k, v := range newData {
        profile[k] = v
    }

    // Конвертируем данные для вставки
    birthdate, _ := profile["birthdate"].(string)
    name, _ := profile["name"].(string)
    gender, _ := profile["gender"].(string)
    age, _ := profile["age"].(int)
    zodiac, _ := profile["zodiac"].(string)
    city, _ := profile["city"].(string)
    region, _ := profile["region"].(string)
    tz, _ := profile["tz"].(string)
    about, _ := profile["about"].(string)
    photoURL, _ := profile["photo_url"].(string)
    createdAt, _ := profile["created_at"].(string)

    db, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return err
    }
    defer db.Close()

    query := `
        INSERT OR REPLACE INTO profiles (
            user_id, name, gender, birthdate, age, zodiac, city, region, tz, about, photo_url, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    `
    _, err = db.Exec(query, userID, name, gender, birthdate, age, zodiac, city, region, tz, about, photoURL, createdAt)
    return err
}

// Получает профиль из базы как map[string]interface{}
func getProfile(userID int64) map[string]interface{} {
    db, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return nil
    }
    defer db.Close()

    row := db.QueryRow(`
        SELECT name, gender, birthdate, age, zodiac, city, region, about, photo_url, is_vip, vip_until
        FROM profiles WHERE user_id=?
    `, userID)

    var name, gender, birthdate, zodiac, city, region, about, photoURL, vipUntil string
    var age int
    var isVIP int

    err = row.Scan(&name, &gender, &birthdate, &age, &zodiac, &city, &region, &about, &photoURL, &isVIP, &vipUntil)
    if err != nil {
        return make(map[string]interface{})
    }

    return map[string]interface{}{
        "name":      name,
        "gender":    gender,
        "birthdate": birthdate,
        "age":       age,
        "zodiac":    zodiac,
        "city":      city,
        "region":    region,
        "about":     about,
        "photo_url": photoURL,
        "is_vip":    isVIP,
        "vip_until": vipUntil,
    }
}

// ================== Обновление активности ==================

// Старт апдейтера last_activity
func startActivityUpdater() {
    for {
        now := time.Now().Unix()
        onlineCount := 0

        mu.Lock()
        for userID, last := range lastActivityCache {
            if now-last > 900 { // 15 минут неактивности
                delete(activeChats, userID)
                rouletteQueue = removeFromQueue(rouletteQueue, userID)
                delete(lastActivityCache, userID)
            } else {
                onlineCount++
            }
        }
        mu.Unlock()
        time.Sleep(60 * time.Second)
    }
}

// Обновление last_activity для пользователя
func updateLastActivity(userID int64) {
    now := time.Now().Unix()
    if db != nil {
        db.Exec("UPDATE profiles SET last_activity=? WHERE user_id=?", now, fmt.Sprint(userID))
    }
}

// ================== Удаление профиля ==================

// Полное удаление профиля
func deleteProfile(userID int64) {
    db, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return
    }
    defer db.Close()

    db.Exec("DELETE FROM profiles WHERE user_id=?", userID)
}

// Мягкое удаление (soft delete) с таймером 30 дней
func softDeleteProfile(userID int64, region string) error {
    deletedAt := time.Now().Add(30 * 24 * time.Hour).Unix()

    conn, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return err
    }
    defer conn.Close()

    _, err = conn.Exec(`
        UPDATE profiles 
        SET deleted_at=? 
        WHERE user_id=? AND deleted_at IS NULL
    `, deletedAt, userID)
    if err != nil {
        return err
    }

    fmt.Printf("User %d будет удалён %d (region %s)\n", userID, deletedAt, region)
    return nil
}

// ================== Работа с отдельными полями ==================
func saveProfileField(chatID int64, field string, value any) {
    query := fmt.Sprintf("UPDATE profiles SET %s = ? WHERE user_id = ?", field)
    _, err := db.Exec(query, value, fmt.Sprintf("%d", chatID))
    if err != nil {
        fmt.Println("DB ERROR:", err)
    }
}

// ================== Статистика ==================
func getStats() (int, int) {
    db, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return 0, 0
    }
    defer db.Close()

    var girls, boys int
    db.QueryRow("SELECT COUNT(*) FROM profiles WHERE gender = 'Ж'").Scan(&girls)
    db.QueryRow("SELECT COUNT(*) FROM profiles WHERE gender = 'М'").Scan(&boys)

    return girls, boys
}

// ================== Создание профиля ==================
func createProfile(userID int64, invitedBy string) error {
    conn, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return err
    }
    defer conn.Close()

    _, err = conn.Exec(`
        INSERT OR IGNORE INTO profiles (user_id, invited_by)
        VALUES (?, ?)
    `, userID, invitedBy)
    return err
}

// ================== Рефералы ==================
func processReferral(inviterID string, invitedID int64) error {
    conn, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return err
    }
    defer conn.Close()

    _, err = conn.Exec(`
        INSERT OR IGNORE INTO referrals (inviter_id, invited_id)
        VALUES (?, ?)
    `, inviterID, invitedID)
    return err
}

// ================== Восстановление профиля ==================
func clearDeletedAt(userID int64) {
    db, _ := sql.Open("sqlite3", DB_FILE)
    defer db.Close()
    db.Exec("UPDATE profiles SET deleted_at=NULL WHERE user_id=?", userID)
}

func restoreProfileInDB(userID int64) error {
    db, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return err
    }
    defer db.Close()

    _, err = db.Exec("UPDATE profiles SET deleted_at=NULL WHERE user_id=?", userID)
    return err
}

// ================== Автоудаление ==================
func startAutoDelete() {
    go func() {
        ticker := time.NewTicker(1 * time.Minute)
        defer ticker.Stop()

        for range ticker.C {
            conn, err := sql.Open("sqlite3", DB_FILE)
            if err != nil {
                continue
            }

            res, err := conn.Exec(`
                DELETE FROM profiles
                WHERE deleted_at IS NOT NULL
                AND deleted_at < strftime('%s','now') - 2592000
            `)
            if err != nil {
                fmt.Println("Ошибка автоудаления:", err)
            } else {
                count, _ := res.RowsAffected()
                if count > 0 {
                    fmt.Printf("Автоудаление: удалено %d профилей\n", count)
                }
            }
            conn.Close()
        }
    }()
}

// ================== Форматирование обратного отсчета ==================
func formatDeleteCountdown(deletedAt int64, tz string) string {
    loc, err := time.LoadLocation(tz)
    if err != nil {
        fmt.Println("TZ LOAD ERROR:", tz, err)
        loc = time.UTC
    }

    t := time.Unix(deletedAt, 0).In(loc)
    now := time.Now().In(loc)
    diff := t.Sub(now)

    if diff <= 0 {
        return fmt.Sprintf("⏳ Анкета будет удалена сегодня в %02d:%02d", t.Hour(), t.Minute())
    }

    days := int(diff.Hours()) / 24
    hours := int(diff.Hours()) % 24
    minutes := int(diff.Minutes()) % 60

    var parts []string

    if days > 0 {
        dayWord := "дней"
        if days%10 == 1 && days%100 != 11 {
            dayWord = "день"
        } else if days%10 >= 2 && days%10 <= 4 && (days%100 < 10 || days%100 >= 20) {
            dayWord = "дня"
        }
        parts = append(parts, fmt.Sprintf("%d %s", days, dayWord))
    }

    if hours > 0 {
        hourWord := "часов"
        if hours%10 == 1 && hours%100 != 11 {
            hourWord = "час"
        } else if hours%10 >= 2 && hours%10 <= 4 && (hours%100 < 10 || hours%100 >= 20) {
            hourWord = "часа"
        }
        parts = append(parts, fmt.Sprintf("%d %s", hours, hourWord))
    }

    if minutes > 0 {
        minWord := "минут"
        if minutes%10 == 1 && minutes%100 != 11 {
            minWord = "минута"
        } else if minutes%10 >= 2 && minutes%10 <= 4 && (minutes%100 < 10 || minutes%100 >= 20) {
            minWord = "минуты"
        }
        parts = append(parts, fmt.Sprintf("%d %s", minutes, minWord))
    }

    if len(parts) == 0 {
        parts = append(parts, "меньше минуты")
    }

    countdown := "через " + strings.Join(parts, " ")
    dateStr := t.Format("02.01.2006")
    timeStr := t.Format("15:04")

    return fmt.Sprintf("❌ Анкета не восстановлена.\nБудет удалена👇\n%s\n(%s в %s)", countdown, dateStr, timeStr)
}

// ================== Обновление deleted_at ==================
func updateProfileDeletedAt(userID int64, ts int64) error {
    conn, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return err
    }
    defer conn.Close()

    stmt, err := conn.Prepare("UPDATE profiles SET deleted_at=? WHERE user_id=?")
    if err != nil {
        return err
    }
    defer stmt.Close()

    _, err = stmt.Exec(ts, userID)
    return err
}

// ================== Конвертация UserState ==================
func stateToMap(state *UserState) map[string]interface{} {
    return map[string]interface{}{
        "name":       state.Name,
        "gender":     state.Gender,
        "birthdate":  fmt.Sprintf("%02d.%02d.%04d", state.BirthDay, state.BirthMonth, state.BirthYear),
        "age":        state.Age,
        "zodiac":     state.Zodiac,
        "city":       state.City,
        "region":     state.Region,
        "tz":         state.Tz,
        "about":      state.About,
        "photo_url":  getPhotoURL(state.Photo),
        "deleted_at": state.DeletedAt,
        "is_vip":     state.IsVIP,
    }
}

// ================== Работа с фото ==================
func getPhotoURL(photo *schemes.PhotoTokens) string {
    if photo == nil || len(photo.Photos) == 0 {
        return ""
    }
    if p, ok := photo.Photos["0"]; ok {
        return p.Token
    }
    for _, v := range photo.Photos {
        return v.Token
    }
    return ""
}

// ================== Загрузка профиля из БД ==================
func loadProfileFromDB(chatID string) (*UserState, error) {
    db, err := sql.Open("sqlite3", DB_FILE)
    if err != nil {
        return nil, err
    }
    defer db.Close()

    row := db.QueryRow(`
        SELECT name, gender, birthdate, age, zodiac, city, region, about, photo_url, is_vip, tz, deleted_at
        FROM profiles
        WHERE user_id = ?
    `, chatID)

    var name, gender, birthdate, zodiac, city, region, about, photoURL, tz string
    var age int
    var isVIPInt int
    var deletedAt sql.NullInt64

    err = row.Scan(&name, &gender, &birthdate, &age, &zodiac, &city, &region, &about, &photoURL, &isVIPInt, &tz, &deletedAt)
    if err != nil {
        return nil, err
    }

    day, month, year := 1, 1, 2000
    fmt.Sscanf(birthdate, "%02d.%02d.%04d", &day, &month, &year)

    state := &UserState{
        ChatID:          parseChatID(chatID),
        Name:            name,
        Gender:          gender,
        BirthDay:        day,
        BirthMonth:      month,
        BirthYear:       year,
        Age:             age,
        Zodiac:          zodiac,
        City:            city,
        Region:          region,
        Tz:              tz,
        About:           about,
        IsVIP:           isVIPInt != 0,
        DeletedAt:       0,
        EditingExisting: true,
    }

    if deletedAt.Valid {
        state.DeletedAt = deletedAt.Int64
    }

    if photoURL != "" {
        state.Photo = &schemes.PhotoTokens{
            Photos: map[string]schemes.PhotoToken{"0": {Token: photoURL}},
        }
    }

    return state, nil
}

// ================== Вспомогательная функция ==================
func parseChatID(chatID string) int64 {
    var id int64
    fmt.Sscanf(chatID, "%d", &id)
    return id
}











///////////////// Универсальный ввод даты рождения
func handleBirthdate(ctx context.Context, api *maxbot.Api, state *UserState, chatID int64, step, text string) {

	switch step {

	// ===== ДЕНЬ =====
	case "birth_day", "edit_birth_day":

		day, err := strconv.Atoi(text)
		if err != nil || day < 1 || day > 31 {
			sendMessage(ctx, api, chatID, "Введите число от 1 до 31")
			return
		}

		state.BirthDay = day

		if strings.HasPrefix(step, "edit_") {
			state.Step = "edit_birth_month"
		} else {
			state.Step = "birth_month"
		}

		sendMessage(ctx, api, chatID, "Введите месяц рождения (1-12)")
		return


	// ===== МЕСЯЦ =====
	case "birth_month", "edit_birth_month":

		month, err := strconv.Atoi(text)
		if err != nil || month < 1 || month > 12 {
			sendMessage(ctx, api, chatID, "Введите число от 1 до 12")
			return
		}

		state.BirthMonth = month

		if strings.HasPrefix(step, "edit_") {
			state.Step = "edit_birth_year"
		} else {
			state.Step = "birth_year"
		}

		sendMessage(ctx, api, chatID, "Введите год рождения")
		return


	
    // ===== ГОД =====
	case "birth_year", "edit_birth_year":

		year, err := strconv.Atoi(text)
		if err != nil {
			sendMessage(ctx, api, chatID, "Введите год числом")
			return
		}

		currentYear := time.Now().Year()

		if year < currentYear-100 || year > currentYear {
			sendMessage(ctx, api, chatID, "Введите корректный год рождения")
			return
		}

        state.BirthYear = year
		
		birthdate := time.Date(year, time.Month(state.BirthMonth), state.BirthDay, 0, 0, 0, 0, time.UTC)

		if birthdate.Day() != state.BirthDay || int(birthdate.Month()) != state.BirthMonth {
			sendMessage(ctx, api, chatID, "Некорректная дата рождения")
			state.Step = "birth_day"
			return
		}

		today := time.Now()
		age := today.Year() - year

		if today.Month() < birthdate.Month() ||
			(today.Month() == birthdate.Month() && today.Day() < birthdate.Day()) {
			age--
		}

		if age < 18 {
			sendMessage(ctx, api, chatID, "Вам должно быть 18+ 🚫")
			state.Step = ""
			return
		}

		state.Birthdate = fmt.Sprintf("%02d.%02d.%04d", state.BirthDay, state.BirthMonth, state.BirthYear)
		state.Age = age
		state.Zodiac = getZodiac(state.BirthDay, state.BirthMonth)

		// ключевая строка
		if strings.HasPrefix(step, "edit_") {
			state.Step = "edit_birth_done"
		} else {
			state.Step = "birth_done"
		}

        handleBirthdate(ctx, api, state, chatID, state.Step, text)
        processProfileCreationEdit(ctx, api, chatID, state, text, nil, "")

		return
	}
}




//////==============фильтры



//////Загрузка фильтров
func loadFilters(chatID int64, state *UserState) {
    var gender sql.NullString
    var ageMin sql.NullInt64
    var ageMax sql.NullInt64
    var city sql.NullString
    var region sql.NullString

    row := db.QueryRow(`
        SELECT filters_gender, filters_age_min, filters_age_max, filters_city, filters_region
        FROM profiles
        WHERE user_id = ?
    `, chatID)

    err := row.Scan(&gender, &ageMin, &ageMax, &city, &region)
    if err != nil {
        fmt.Println("[DEBUG] loadFilters error:", err)
    }

    // Пол
    if gender.Valid {
        state.Gender = gender.String
    } else {
        state.Gender = "Любой"
    }

    // Возраст
    if ageMin.Valid {
        state.FilterAgeMin = int(ageMin.Int64)
    } else {
        state.FilterAgeMin = 18
    }

    if ageMax.Valid {
        state.FilterAgeMax = int(ageMax.Int64)
    } else {
        state.FilterAgeMax = 35
    }

    // Город
    if city.Valid {
        state.City = city.String
    } else {
        state.City = ""
    }

    // Регион
    if region.Valid {
        state.Region = region.String
    } else {
        state.Region = ""
    }

}


// ================= ПОЛУЧИТЬ ФИЛЬТРЫ =================

func GetFilters(userID int64) Filters {

	var f Filters

	err := db.QueryRow(`
	SELECT
		filters_city,
		filters_region,
		filters_gender,
		filters_age_min,
		filters_age_max
	FROM profiles
	WHERE user_id = ?
	`, userID).Scan(
		&f.City,
		&f.Region,
		&f.Gender,
		&f.AgeMin,
		&f.AgeMax,
	)

	if err != nil {

		f.City = "Любой"
		f.Region = "Любой"
		f.Gender = "Любой"
		f.AgeMin = 18
		f.AgeMax = 35

		return f
	}

	if f.City == "" {
		f.City = "Любой"
	}

	if f.Region == "" {
		f.Region = "Любой"
	}

	if f.Gender == "" {
		f.Gender = "Любой"
	}

	if f.AgeMin == 0 {
		f.AgeMin = 18
	}

	if f.AgeMax == 0 {
		f.AgeMax = 35
	}

	return f
}


// ================= СОХРАНИТЬ ФИЛЬТР =================

func UpdateFilter(userID int64, field string, value any) {

	allowed := map[string]bool{
		"filters_city":    true,
		"filters_region":  true,
		"filters_gender":  true,
		"filters_age_min": true,
		"filters_age_max": true,
	}

	if !allowed[field] {
		return
	}

	query := fmt.Sprintf("UPDATE profiles SET %s=? WHERE user_id=?", field)

	_, err := db.Exec(query, value, userID)

	if err != nil {
		fmt.Println("filter save error:", err)
	}
}


// ================= СБРОС ФИЛЬТРОВ =================

func ResetFilters(userID int64) {
	_, err := db.Exec(`
	UPDATE profiles
	SET
		filters_city = '',
		filters_region = '',
		filters_gender = 'Любой',
		filters_age_min = 18,
		filters_age_max = 35
	WHERE user_id = ?
	`, userID)

	if err != nil {
		fmt.Println("reset filters error:", err)
	}
}





//======КЛАВИАТУРА ФИЛЬТРЫ
//======КЛАВИАТУРА ФИЛЬТРЫ
func showFilters(ctx context.Context, api *maxbot.Api, chatID int64, state *UserState) {
    // Загружаем фильтры из базы
    loadFilters(chatID, state)

    // Пол
    gender := strings.TrimSpace(state.Gender)
    var genderText string = "🎭 Любой"

    switch gender {
    case "М":
        genderText = "👨 Парни"
    case "Ж":
        genderText = "👩 Девушки"
    }

    // Возраст из state
    minAge := state.FilterAgeMin
    maxAge := state.FilterAgeMax
    if minAge == 0 {
        minAge = 18
    }
    if maxAge == 0 {
        maxAge = 35
    }

    // Город (Область)
    city := "Любой"
    if state.City != "" {
        city = state.City
        if state.Region != "" {
            city += " (" + state.Region + ")"
        }
    }

    // Формируем текст — используем genderText вместо gender и emoji
    text := fmt.Sprintf(
        "⚙️ Ваши фильтры:\n\nПол: %s\nВозраст: %d–%d\nГород: %s",
        genderText, minAge, maxAge, city,
    )

    // Клавиатура
    keyboard := api.Messages.NewKeyboardBuilder()

    keyboard.AddRow().
        AddCallback("Пол: "+genderText, schemes.DEFAULT, "gender_filters")

    keyboard.AddRow().
        AddCallback(fmt.Sprintf("Возраст: %d-%d", minAge, maxAge), schemes.DEFAULT, "age_filters")

    keyboard.AddRow().
        AddCallback("Город: "+city, schemes.DEFAULT, "city_filters")

    keyboard.AddRow().
        AddCallback("Сбросить фильтры", schemes.NEGATIVE, "filters_reset")

    keyboard.AddRow().
        AddCallback("Готово", schemes.POSITIVE, "main_menu")

    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText(text).
        AddKeyboard(keyboard)

    api.Messages.Send(ctx, msg)
}


// Отправка клавиатуры возраста
func sendAgeKeyboard(ctx context.Context, api *maxbot.Api, chatID int64, minAge, maxAge int) {
    kb := api.Messages.NewKeyboardBuilder()

    kb.AddRow().
        AddCallback("⬅️ Мин -1", schemes.DEFAULT, "age_min_minus").
        AddCallback(fmt.Sprintf("%d", minAge), schemes.DEFAULT, "noop").
        AddCallback("Мин +1 ➡️", schemes.DEFAULT, "age_min_plus")

    kb.AddRow().
        AddCallback("⬅️ Макс -1", schemes.DEFAULT, "age_max_minus").
        AddCallback(fmt.Sprintf("%d", maxAge), schemes.DEFAULT, "noop").
        AddCallback("Макс +1 ➡️", schemes.DEFAULT, "age_max_plus")

    kb.AddRow().
        AddCallback("✅ Готово", schemes.DEFAULT, "done_filters")

    api.Messages.Send(ctx, maxbot.NewMessage().
        SetChat(chatID).
        SetText("Выберите возраст").
        AddKeyboard(kb),
    )
}
///==============================Пригласительный
////////Пригласить друзей
func inviteMessage(userID int64) (string, *maxbot.Keyboard) {

    db, _ := sql.Open("sqlite3", DB_FILE)
    defer db.Close()

    var totalInvited int
    db.QueryRow("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", userID).Scan(&totalInvited)

    var invites int
    db.QueryRow("SELECT invites FROM profiles WHERE user_id=?", userID).Scan(&invites)

    total := 3
    vipAwarded := false

    if invites >= total {

        vipUntil := time.Now().Add(24 * time.Hour)

        db.Exec(`
            UPDATE profiles
            SET vip_until=?, invites=invites-?
            WHERE user_id=?
        `, vipUntil.Format("2006-01-02 15:04:05"), total, userID)

        invites -= total
        vipAwarded = true
    }

    filled := invites
    if filled > total {
        filled = total
    }

    progress := strings.Repeat("█", filled) + strings.Repeat("░", total-filled)
    remaining := total - invites
    if remaining < 0 {
        remaining = 0
    }

    var header string

    if vipAwarded {

        header = fmt.Sprintf(
            "🎉🔥 Ты пригласил %d друзей!\n\n💎 VIP активирован на 24 часа!\n\n👥 Всего приглашено: %d\n🚀 Продолжай приглашать и получай ещё VIP!",
            total, total,
        )

    } else {

        header = fmt.Sprintf(
            "👥 Ты уже пригласил: %d\n\n🧑‍🤝‍🧑 Прогресс: %d / %d %s\n🔥 Осталось %d до VIP!",
            totalInvited, invites, total, progress, remaining,
        )
    }

    inviteLink := fmt.Sprintf("https://max.ru/%s?start=%d", BOT_USERNAME, userID)

    text := fmt.Sprintf(
        "🎁 Получай VIP бесплатно!\n\n%s\n\n📩 Твоя персональная ссылка:\n%s\n\nОтправь её друзьям и получай бонусы 💬🔥\n\n💎 За каждых %d друзей — 1 день VIP",
        header,
        inviteLink,
        total,
    )

    keyboard := &maxbot.Keyboard{}
    keyboard.AddRow().
        AddCallback("🏠 Главное меню", schemes.DEFAULT, "main_menu")

    return text, keyboard
}

func CreateProfile(userID int64, invitedBy *int64) {
	db, _ := sql.Open("sqlite3", DB_FILE)
	defer db.Close()

	_, err := db.Exec(`
		INSERT INTO profiles (
			user_id, name, gender, birthdate, age, zodiac,
			city, region, about, photo_url, is_vip,
			invites, vip_until, invited_by
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`,
		userID, "", "", "", 0, "",
		"", "", "", "", 0,
		0, nil, invitedBy,
	)

	if err != nil {
		fmt.Println("CreateProfile error:", err)
	}
}

func CreateProfileIfNotExists(userID int64) {
	db, _ := sql.Open("sqlite3", DB_FILE)
	defer db.Close()

	var exists int

	err := db.QueryRow(`
		SELECT 1 FROM profiles WHERE user_id = ?
	`, userID).Scan(&exists)

	if err != nil {
		_, err := db.Exec(`
			INSERT INTO profiles (user_id, invites, vip_until)
			VALUES (?, 0, NULL)
		`, userID)

		if err != nil {
			fmt.Println("CreateProfileIfNotExists error:", err)
		} else {
			fmt.Println("PROFILE CREATED:", userID)
		}
	}
}

func ProcessReferral(inviterID, invitedID int64) {
	if inviterID == invitedID {
		return
	}

	db, _ := sql.Open("sqlite3", DB_FILE)
	defer db.Close()

	var exists int

	err := db.QueryRow(`
		SELECT 1 FROM referrals WHERE invited_id = ?
	`, invitedID).Scan(&exists)

	if err == nil {
		return // уже был
	}

	// записываем
	_, err = db.Exec(`
		INSERT INTO referrals (inviter_id, invited_id)
		VALUES (?, ?)
	`, inviterID, invitedID)

	if err != nil {
		fmt.Println("ProcessReferral insert error:", err)
		return
	}

	// увеличиваем invites
	_, err = db.Exec(`
		UPDATE profiles
		SET invites = COALESCE(invites, 0) + 1
		WHERE user_id = ?
	`, inviterID)

	if err != nil {
		fmt.Println("ProcessReferral update error:", err)
	}
}

func RegisterNewUser(userID int64, inviterID int64) {

	if inviterID != 0 && inviterID != userID {

		var exists int

		err := db.QueryRow(`
			SELECT 1 FROM referrals WHERE invited_id = ?
		`, userID).Scan(&exists)

		if err == nil {
			fmt.Println("Уже приглашён:", userID)
			return
		}

		_, err = db.Exec(`
			INSERT INTO referrals (inviter_id, invited_id)
			VALUES (?, ?)
		`, inviterID, userID)

		if err != nil {
			fmt.Println("RegisterNewUser insert error:", err)
			return
		}

		AddInvite(inviterID)

		fmt.Println("OK:", inviterID, "пригласил", userID)
	}
}

func profileExists(chatID int64) bool {
    var exists int
    err := db.QueryRow(`
        SELECT 1 FROM profiles WHERE user_id = ?
    `, chatID).Scan(&exists)

    return err == nil
}

func AddInvite(userID int64) {
	db, _ := sql.Open("sqlite3", DB_FILE)
	defer db.Close()

	// +1 приглашение
	_, _ = db.Exec(`
		UPDATE profiles
		SET invites = COALESCE(invites, 0) + 1
		WHERE user_id = ?
	`, userID)

	var invites int

	_ = db.QueryRow(`
		SELECT invites FROM profiles WHERE user_id = ?
	`, userID).Scan(&invites)

	if invites >= 3 {

		vipUntil := time.Now().Add(24 * time.Hour)

		_, _ = db.Exec(`
			UPDATE profiles
			SET vip_until = ?, invites = invites - 3
			WHERE user_id = ?
		`, vipUntil.Format("2006-01-02 15:04:05"), userID)

		fmt.Println("VIP выдан:", userID)
	}
}

////====================Админ панель
func ShowAdminPanel(api *maxbot.Api, chatID int64) {
	// Открываем базу
	db, err := sql.Open("sqlite3", DB_FILE)
	if err != nil {
		log.Println("DB open error:", err)
		return
	}
	defer db.Close()

	// Получаем статистику
	stats := GetStats()
	if err != nil {
		log.Println("Ошибка получения статистики:", err)
		sendMessage(nil, api, chatID, "❌ Ошибка при получении статистики")
		return
	}

	// Формируем текст
	text := fmt.Sprintf(
		"📊 Админ-панель\n\n"+
			"👥 Пользователи:\n"+
			"• Всего: %d\n"+
			"• Мужчин: %d\n"+
			"• Женщин: %d\n\n"+
			"💎 VIP подписка:\n"+
			"• Всего VIP: %d\n"+
			"• Мужчин VIP: %d\n"+
			"• Женщин VIP: %d\n\n"+
			"🎰 Рулетка:\n"+
			"🟢 Онлайн: %d\n"+
			"⏳ В очереди: %d\n"+
			"💬 Активных чатов: %d\n"+
			"🔎 Поисков всего: %d\n"+
			"🎉 Совпадений: %d",
		stats.UsersTotal, stats.UsersM, stats.UsersF,
		stats.VIPTotal, stats.VIPM, stats.VIPF,
		stats.Online, stats.WaitingQueue, stats.ActiveChats,
		stats.TotalSearches, stats.TotalMatches,
	)

	// Клавиатура
	kb := api.Messages.NewKeyboardBuilder()
	if IsVIP(chatID) {
		kb.AddRow().AddCallback("❌ Отключить VIP (у меня)", schemes.DEFAULT, "admin_vip_off")
	} else {
		kb.AddRow().AddCallback("✅ Включить VIP (у меня)", schemes.DEFAULT, "admin_vip_on")
	}

	kb.AddRow().AddCallback("⏳ Таймер чата", schemes.DEFAULT, "admin_timer")
	kb.AddRow().AddCallback("🔄 Обновить", schemes.DEFAULT, "admin_refresh")
	kb.AddRow().AddCallback("⬅ Назад", schemes.DEFAULT, "main_menu")

	// Сообщение
	msg := maxbot.NewMessage().
		SetChat(chatID).
		SetText(text).
		AddKeyboard(kb)

	// Отправляем
	err = api.Messages.Send(context.Background(), msg)
	if err != nil {
		log.Println("Send error:", err)
	}
}


// Получение статистики из базы
// ================= СТАТИСТИКА =================



// GetStats собирает статистику
func GetStats() Stats {
    now := time.Now().Unix()
    s := Stats{}

    // Пользователи
    db.QueryRow("SELECT COUNT(*) FROM profiles").Scan(&s.UsersTotal)
    db.QueryRow("SELECT COUNT(*) FROM profiles WHERE gender='М'").Scan(&s.UsersM)
    db.QueryRow("SELECT COUNT(*) FROM profiles WHERE gender='Ж'").Scan(&s.UsersF)

    // VIP
    db.QueryRow("SELECT COUNT(*) FROM profiles WHERE is_vip=1 AND (vip_until IS NULL OR strftime('%s', vip_until) > ?)", now).Scan(&s.VIPTotal)
    db.QueryRow("SELECT COUNT(*) FROM profiles WHERE gender='М' AND is_vip=1 AND (vip_until IS NULL OR strftime('%s', vip_until) > ?)", now).Scan(&s.VIPM)
    db.QueryRow("SELECT COUNT(*) FROM profiles WHERE gender='Ж' AND is_vip=1 AND (vip_until IS NULL OR strftime('%s', vip_until) > ?)", now).Scan(&s.VIPF)
    
	// Онлайн (last_activity за 5 минут)
	db.QueryRow("SELECT COUNT(*) FROM profiles WHERE last_activity>? ", now-300).Scan(&s.Online)

    // Рулетка
    db.QueryRow("SELECT COUNT(*) FROM roulette_queue").Scan(&s.WaitingQueue)
    db.QueryRow("SELECT COUNT(*) FROM active_chats").Scan(&s.ActiveChats)

    // Поисков и матчей
    db.QueryRow("SELECT COUNT(*) FROM search_history").Scan(&s.TotalSearches)
    db.QueryRow("SELECT COUNT(*) FROM match_history").Scan(&s.TotalMatches)

    return s
}

// ================= ЛОГИРУЕМ СОБЫТИЯ РУЛЕТКИ =================

func logRouletteEvent(userID, event string, partnerID string) {
    ts := time.Now().Unix()
    db.Exec("INSERT INTO roulette_stats (timestamp, user_id, event, partner_id) VALUES (?, ?, ?, ?)",
        ts, userID, event, partnerID)
}

func logSearch(userID string) {
    ts := time.Now().Unix()
    db.Exec("INSERT INTO search_history (user_id, searched_at) VALUES (?, ?)", userID, ts)
    logRouletteEvent(userID, "search", "")
}

func logMatch(userID, partnerID string) {
    ts := time.Now().Unix()
    db.Exec("INSERT INTO match_history (user1_id, user2_id, matched_at) VALUES (?, ?, ?)", userID, partnerID, ts)
    logRouletteEvent(userID, "match", partnerID)
}

func logChatStarted(userID, partnerID string) {
    logRouletteEvent(userID, "chat_started", partnerID)
}

func logChatEnded(userID, partnerID string) {
    logRouletteEvent(userID, "chat_ended", partnerID)
}


























// Получить текущий таймер из базы
func GetChatTimer() int {
    var timer int

    err := db.QueryRow(`
        SELECT value FROM bot_settings WHERE key='chat_timer'
    `).Scan(&timer)

    if err != nil {
        fmt.Println("GetChatTimer error:", err)
        return 180 // дефолт как у тебя в базе
    }

    return timer
}

// Установить новый таймер
func SetChatTimer(seconds int) {
    _, err := db.Exec(`
        UPDATE bot_settings SET value=? WHERE key='chat_timer'
    `, seconds)

    if err != nil {
        fmt.Println("SetChatTimer error:", err)
    } else {
        fmt.Println("TIMER SAVED:", seconds)
    }
}





func IsVIP(userID int64) bool {
	var vipUntil string

	err := db.QueryRow(`
		SELECT vip_until FROM profiles WHERE user_id=?
	`, userID).Scan(&vipUntil)

	if err != nil || vipUntil == "" {
		return false
	}

	t, err := time.Parse("2006-01-02 15:04:05", vipUntil)
	if err != nil {
		return false
	}

	return t.After(time.Now())
}
































/////////////==========ВИП
func vip_keyboard() *maxbot.Keyboard {
	kb := &maxbot.Keyboard{}

	// Тарифы
	kb.AddRow().AddCallback("💳 VIP 30 дней — 300 ₽", schemes.DEFAULT, "vip_30")
	kb.AddRow().AddCallback("💳 VIP 6 месяцев — 1500 ₽", schemes.DEFAULT, "vip_180")
	kb.AddRow().AddCallback("💳 VIP 12 месяцев — 2500 ₽", schemes.DEFAULT, "vip_365")

	// Кнопка назад
	kb.AddRow().AddCallback("⬅️ Назад", schemes.DEFAULT, "main_menu")

	return kb
}

func vip_offer_keyboard() *maxbot.Keyboard {
	kb := &maxbot.Keyboard{}
	kb.AddRow().AddCallback("✅ Согласен", schemes.DEFAULT, "offer_accept")
	kb.AddRow().AddCallback("❌ Не согласен", schemes.DEFAULT, "offer_decline")
	return kb
}

func VIPStartKeyboard() *maxbot.Keyboard {
	kb := &maxbot.Keyboard{}
	kb.AddRow().AddCallback("📄 Условия оферты", schemes.DEFAULT, "show_offer")
	kb.AddRow().AddCallback("💎 Оформить VIP", schemes.DEFAULT, "vip_tarif")
	kb.AddRow().AddCallback("⬅️ Назад", schemes.DEFAULT, "back")
	return kb
}

func PayKeyboard(payURL string) *maxbot.Keyboard {
    kb := &maxbot.Keyboard{}
    kb.AddRow().AddLink("🔗 Перейти к оплате", schemes.POSITIVE, payURL)
    kb.AddRow().AddCallback("⬅️ Назад", schemes.DEFAULT, "vip_tariv")
    return kb
}

const OFFER_TEXT = `📄 *ПУБЛИЧНАЯ ОФЕРТА*

Настоящая публичная оферта (далее — Оферта) устанавливает условия предоставления услуг подписки на чат-рулетку знакомств (далее — Услуги) индивидуальным предпринимателем (далее — Исполнитель).
Оферта является предложением заключить договор на условиях, изложенных ниже.

*1. Предмет договора*
1.1. Исполнитель обязуется предоставить Пользователю доступ к Услугам подписки на чат-рулетку знакомств, а Пользователь обязуется оплатить подписку на условиях, изложенных в настоящей Оферте.

1.2. Услуги включают в себя:
• Общение в чате-рулетке без ограничений по времени  
• Доступ к дополнительным функциям и привилегиям

*2. Стоимость и порядок оплаты*
2.1. Стоимость подписки:
• 30 дней — 300 ₽  
• 6 месяцев — 1500 ₽  
• 12 месяцев — 2500 ₽  

2.2. Оплата производится в форме предоплаты.
Возврат средств не осуществляется, за исключением случаев, предусмотренных законодательством РФ.

*3. Условия использования*
3.1. Пользователь обязуется соблюдать нормы этики и морали, не распространять спам и не нарушать права других пользователей.

*4. Ограничения без подписки*
4.1. Пользователи без подписки могут общаться в чате не более 3 минут, после чего диалог автоматически завершается.

*5. Конфиденциальность*
5.1. Исполнитель обеспечивает защиту персональных данных в соответствии с законодательством РФ.

*6. Заключительные положения*
6.1. Оферта вступает в силу с момента её акцепта Пользователем.

📄 *Исполнитель услуг:*
ИП Мерзляков Алексей Владимирович  
ИНН: 420105283818  
ОГРНИП: 324420500025722
`



const VIP_TEXT = `Подключая подписку VIP чата-рулетки знакомств, вы соглашаетесь с условиями оферты.

📄 Исполнитель услуг:
Индивидуальный предприниматель
Мерзляков Алексей Владимирович
ИНН: 420105283818
ОГРНИП: 324420500025722

💳 Оплата производится в форме предоплаты.
🔁 Возврат средств не производится, за исключением случаев невозможности оказания услуги по техническим причинам.

📦 Тарифы VIP-подписки:
• 30 дней — 300 ₽
• 6 месяцев — 1500 ₽
• 12 месяцев — 2500 ₽
`



// ===== Проверка статуса платежей =====
// Проверка и активация VIP
func pollPaymentsYooKassa(api *maxbot.Api) {
	for {
		//fmt.Println("\n[POLL] ===== проверка =====")

		db, err := sql.Open("sqlite3", DB_FILE+"?_busy_timeout=5000&_journal_mode=WAL")
		if err != nil {
			fmt.Println("[POLL] DB error:", err)
			time.Sleep(30 * time.Second)
			continue
		}

		rows, err := db.Query(`SELECT id, chat_id, payment_id, days FROM payments WHERE status='pending'`)
		if err != nil {
			fmt.Println("[POLL] query error:", err)
			db.Close()
			time.Sleep(30 * time.Second)
			continue
		}

		for rows.Next() {
			var dbID int
			var chatID int64
			var paymentID string
			var days int

			err := rows.Scan(&dbID, &chatID, &paymentID, &days)
			if err != nil {
				fmt.Println("[POLL] Scan error:", err)
				continue
			}

			fmt.Println("[POLL] checking payment:", paymentID)
			status := checkPaymentStatus(paymentID)
			if status != "succeeded" {
				continue
			}

			fmt.Println("[POLL] ✅ ОПЛАЧЕНО!")

			// ===== ПРОДЛЕНИЕ VIP =====
			var currentVIP sql.NullString
			err = db.QueryRow("SELECT vip_until FROM profiles WHERE user_id=?", chatID).Scan(&currentVIP)
			if err != nil {
				fmt.Println("[POLL] Ошибка чтения VIP:", err)
			}

			baseTime := time.Now()
			if currentVIP.Valid {
				parsed, err := time.Parse("2006-01-02 15:04:05", currentVIP.String)
				if err == nil && parsed.After(time.Now()) {
					baseTime = parsed
				}
			}

			vipUntil := baseTime.AddDate(0, 0, days)
			vipUntilStr := vipUntil.Format("2006-01-02 15:04:05")
			fmt.Println("[POLL] VIP до:", vipUntilStr)

			// ===== Обновление VIP и удаление платежа в транзакции =====
			tx, err := db.Begin()
			if err != nil {
				fmt.Println("[POLL] Ошибка начала транзакции:", err)
				continue
			}

			_, err = tx.Exec("UPDATE profiles SET vip_until=?, is_vip=1 WHERE user_id=?", vipUntilStr, chatID)
			if err != nil {
				fmt.Println("[POLL] Ошибка обновления VIP:", err)
				tx.Rollback()
				continue
			}

			res, err := tx.Exec("DELETE FROM payments WHERE id=?", dbID)
			if err != nil {
				fmt.Println("[POLL] Ошибка удаления платежа:", err)
				tx.Rollback()
				continue
			}

			affected, _ := res.RowsAffected()
			fmt.Println("[POLL] платеж удалён, rows affected:", affected)

			tx.Commit()

			// ===== Отправка сообщения пользователю =====
			state := users[chatID]
			if state == nil {
				state = &UserState{ChatID: chatID}
				users[chatID] = state
			}

			text, kb := main_menu(api, chatID, state)
			msg := maxbot.NewMessage().
				SetChat(chatID).
				SetText(fmt.Sprintf(
					"🎉 VIP активирован на %d дней!\nДо %s\n\nСпасибо за поддержку ❤️\n\n%s",
					days,
					vipUntil.Format("02.01.2006 15:04"),
					text,
				)).
				AddKeyboard(kb)

			if err := api.Messages.Send(context.Background(), msg); err != nil {
				fmt.Println("[POLL] Ошибка отправки сообщения:", err)
			}
		}

		rows.Close()
		db.Close()
		time.Sleep(30 * time.Second)
	}
}












func isVIP(vipUntil string) bool {
	if vipUntil == "" {
		return false
	}

	t, err := time.Parse("2006-01-02 15:04:05", vipUntil)
	if err != nil {
		return false
	}

	return t.After(time.Now())
}


func activateVIP(chatID int64, days int) string {
	userID := fmt.Sprint(chatID)

	var currentVIP sql.NullString
	err := db.QueryRow("SELECT vip_until FROM profiles WHERE user_id=?", userID).Scan(&currentVIP)

	now := time.Now()
	var newTime time.Time

	if err == nil && currentVIP.Valid && currentVIP.String != "" {
		parsed, err := time.Parse("2006-01-02 15:04:05", currentVIP.String)
		if err == nil && parsed.After(now) {
			newTime = parsed.AddDate(0, 0, days)
		} else {
			newTime = now.AddDate(0, 0, days)
		}
	} else {
		newTime = now.AddDate(0, 0, days)
	}

	vipUntil := newTime.Format("2006-01-02 15:04:05")

	_, err = db.Exec(`
		UPDATE profiles 
		SET is_vip=1, vip_until=? 
		WHERE user_id=?
	`, vipUntil, userID)

	if err != nil {
		fmt.Println("VIP UPDATE ERROR:", err)
	}

	return vipUntil
}

func deactivateVIP(chatID int64) {
	userID := fmt.Sprint(chatID)

	_, err := db.Exec(`
		UPDATE profiles 
		SET is_vip=0, vip_until=NULL 
		WHERE user_id=?
	`, userID)

	if err != nil {
		fmt.Println("VIP OFF ERROR:", err)
	}
}


// Сохраняем платеж в базе
func saveOrder(paymentID string, chatID int64, days int) {
	db, _ := sql.Open("sqlite3", DB_FILE)
	defer db.Close()

	_, err := db.Exec(`
		INSERT INTO payments (chat_id, payment_id, days, status)
		VALUES (?, ?, ?, 'pending')
	`, chatID, paymentID, days)

	if err != nil {
		fmt.Println("[DB] save error:", err)
	} else {
		fmt.Println("[DB] saved payment:", paymentID)
	}
}


// Создаём платёж через YooKassa и возвращаем URL
func createPayment(amount int, description string, chatID int64, days int) (*YooPayment, error) {
	url := "https://api.yookassa.ru/v3/payments"

	data := map[string]interface{}{
		"amount": map[string]interface{}{
			"value":    fmt.Sprintf("%.2f", float64(amount)),
			"currency": "RUB",
		},
		"confirmation": map[string]interface{}{
			"type":       "redirect",
			"return_url": "https://example.com", // можно любой
		},
		"capture": true,
		"description": description,
		"metadata": map[string]interface{}{
			"chat_id": chatID,
			"days":    days,
		},
	}

	bodyBytes, _ := json.Marshal(data)

	req, _ := http.NewRequest("POST", url, bytes.NewReader(bodyBytes))

	auth := base64.StdEncoding.EncodeToString([]byte(YOOKASSA_SHOP_ID + ":" + YOOKASSA_SECRET_KEY))
	req.Header.Set("Authorization", "Basic "+auth)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotence-Key", fmt.Sprintf("%d_%d", chatID, time.Now().Unix()))

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	fmt.Println("[YOOKASSA CREATE]:", string(respBody))

	var payment YooPayment
	json.Unmarshal(respBody, &payment)

	return &payment, nil
}



func checkPaymentStatus(paymentID string) string {
	req, _ := http.NewRequest("GET", "https://api.yookassa.ru/v3/payments/"+paymentID, nil)
	req.SetBasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Println("YooKassa API error:", err)
		return "error"
	}
	defer resp.Body.Close()

	var result struct {
		Status string `json:"status"`
	}
	err = json.NewDecoder(resp.Body).Decode(&result)
	if err != nil {
		fmt.Println("YooKassa decode error:", err)
		return "error"
	}

	return result.Status // "pending", "succeeded", "canceled"
}


























// ================== ПОЛУЧЕНИЕ ФИЛЬТРОВ ==================
func getFilters(userID int64) (city, gender string, ageMin, ageMax int) {
    profile, ok := users[userID]
    if !ok {
        return "Любой", "Любой", 18, 35
    }

    city = profile.FilterCity
    if city == "" {
        city = "Любой"
    }
    gender = profile.FilterGender
    if gender == "" {
        gender = "Любой"
    }
    ageMin = profile.FilterAgeMin
    if ageMin == 0 {
        ageMin = 18
    }
    ageMax = profile.FilterAgeMax
    if ageMax == 0 {
        ageMax = 35
    }
    return
}


// ================== РУЛЕТКА ==================
// ================== ПОИСК СОБЕСЕДНИКА ==================
func rouletteIn(ctx context.Context, api *maxbot.Api, chatID int64) {
    userID := chatID
    //logSearch(fmt.Sprint(userID))

    // ================== ПОЛУЧАЕМ ПРОФИЛЬ ==================
    mu.Lock()
    profile, ok := users[userID]
    mu.Unlock()

    if !ok || profile == nil {
        dbProfile, err := loadProfileFromDB(fmt.Sprintf("%d", userID))
        if err != nil || dbProfile == nil {
            sendMessage(ctx, api, chatID, "❗ Профиль не найден. Сначала заполните анкету.")
            return
        }

        mu.Lock()
        users[userID] = dbProfile
        profile = dbProfile
        mu.Unlock()
    }

    // ================== ПРОВЕРКА: УЖЕ В ЧАТЕ ==================
    mu.Lock()
    if _, inChat := activeChats[userID]; inChat {
        mu.Unlock()
        sendMessage(ctx, api, chatID, "❗ Вы уже в чате")
        return
    }

    // ================== ДОБАВЛЯЕМ В ОЧЕРЕДЬ ==================
    db.Exec("INSERT OR IGNORE INTO roulette_queue (user_id, joined_at) VALUES (?, ?)", userID, time.Now().Unix())

    if profile.IsVIP {
        rouletteQueue = append([]int64{userID}, rouletteQueue...)
    } else {
        rouletteQueue = append(rouletteQueue, userID)
    }

    // Удаляем дубли
    rouletteQueue = uniqueQueue(rouletteQueue)

    //fmt.Println("[IN] user joined roulette:", userID)
    //fmt.Println("[QUEUE]", rouletteQueue)
    //fmt.Println("[ACTIVE_CHATS]", activeChats)

    // Делаем копию очереди (чтобы не было race condition)
    queueCopy := append([]int64{}, rouletteQueue...)

    mu.Unlock()

    // Сообщение "ищем"
    sendSearchingMessage(ctx, api, chatID)

    var partnerID int64 = 0

    // ================== ПОИСК СОБЕСЕДНИКА ==================
    for _, candidate := range queueCopy {

        // защита от самого себя
        if candidate == userID {
            continue
        }

        mu.Lock()
        p := users[candidate]
        mu.Unlock()

        // если нет профиля — подгружаем
        if p == nil {
            dbProfile, err := loadProfileFromDB(fmt.Sprintf("%d", candidate))
            if err != nil || dbProfile == nil {
                continue
            }

            mu.Lock()
            users[candidate] = dbProfile
            mu.Unlock()

            p = dbProfile
        }

        // ================== ФИЛЬТРЫ ==================

        if profile.FilterCity != "Любой" && profile.FilterCity != p.City {
            //fmt.Println("[FILTER] city mismatch:", userID, "->", candidate)
            continue
        }

        if p.FilterCity != "Любой" && p.FilterCity != profile.City {
            //fmt.Println("[FILTER] city mismatch:", candidate, "->", userID)
            continue
        }

        if profile.FilterGender != "Любой" && profile.FilterGender != p.Gender {
            //fmt.Println("[FILTER] gender mismatch:", userID, "->", candidate)
            continue
        }

        if p.FilterGender != "Любой" && p.FilterGender != profile.Gender {
            //fmt.Println("[FILTER] gender mismatch:", candidate, "->", userID)
            continue
        }

        if !(profile.FilterAgeMin <= p.Age && p.Age <= profile.FilterAgeMax) {
            //fmt.Println("[FILTER] age mismatch:", userID, "->", candidate)
            continue
        }

        if !(p.FilterAgeMin <= profile.Age && profile.Age <= p.FilterAgeMax) {
            //fmt.Println("[FILTER] age mismatch:", candidate, "->", userID)
            continue
        }

        // нашли партнёра
        partnerID = candidate
        break
    }

    // ================== ЕСЛИ НЕ НАШЛИ ==================
    if partnerID == 0 {
        //fmt.Println("❌ Партнёр не найден:", queueCopy)
        return
    }

    // ================== СОЗДАЁМ ЧАТ ==================
    mu.Lock()

    // удаляем из очереди
    rouletteQueue = removeFromQueue(rouletteQueue, userID)
    rouletteQueue = removeFromQueue(rouletteQueue, partnerID)

    // создаём пару
    activeChats[userID] = partnerID
    activeChats[partnerID] = userID

    mu.Unlock()

    db.Exec("DELETE FROM roulette_queue WHERE user_id IN (?, ?)", userID, partnerID)
    db.Exec("INSERT INTO active_chats (user1, user2) VALUES (?, ?)", userID, partnerID)

    //fmt.Printf("✅ CONNECT %d ↔ %d\n", userID, partnerID)
    //fmt.Println("[QUEUE]", rouletteQueue)
    //fmt.Println("[ACTIVE_CHATS]", activeChats)

    // ================== КНОПКА ВЫХОДА ==================
    leaveKeyboard := api.Messages.NewKeyboardBuilder()
    leaveKeyboard.AddRow().AddCallback("⏹ Выйти из чата", schemes.DEFAULT, "roulette_out")

    // ================== ОБНОВЛЯЕМ ПРОФИЛИ ==================
    if dbProfile, err := loadProfileFromDB(fmt.Sprintf("%d", partnerID)); err == nil && dbProfile != nil {
        mu.Lock()
        users[partnerID] = dbProfile
        mu.Unlock()
    }

    if dbProfile, err := loadProfileFromDB(fmt.Sprintf("%d", userID)); err == nil && dbProfile != nil {
        mu.Lock()
        users[userID] = dbProfile
        mu.Unlock()
    }

    // ================== ПОКАЗ ПРОФИЛЕЙ ==================
    showProfile(ctx, api, userID, users[partnerID], leaveKeyboard)
    showProfile(ctx, api, partnerID, users[userID], leaveKeyboard)

    // ================== ТАЙМЕР ==================
    go chatTimer(api, userID, partnerID)
}

// ================== ВЫХОД ИЗ ЧАТА ==================
func rouletteOut(ctx context.Context, api *maxbot.Api, chatID int64) {
    mu.Lock()
    partnerID, ok := activeChats[chatID]

    if ok {
        delete(activeChats, chatID)
        delete(activeChats, partnerID)
    }

    rouletteQueue = removeFromQueue(rouletteQueue, chatID)
    if ok && partnerID != 0 {
        rouletteQueue = removeFromQueue(rouletteQueue, partnerID)
    }
    rouletteQueue = uniqueQueue(rouletteQueue)
	
    if !ok {
        //fmt.Println("[OUT] user не был в чате:", chatID)
    }
	
    mu.Unlock()

    // ===== УДАЛЯЕМ ИЗ БД =====
    db.Exec("DELETE FROM active_chats WHERE user1=? OR user2=?", chatID, chatID)
    db.Exec("DELETE FROM roulette_queue WHERE user_id=?", chatID)
    if ok && partnerID != 0 {
        db.Exec("DELETE FROM roulette_queue WHERE user_id=?", partnerID)
    }

    // ===== ЛОГИ =====
    //fmt.Println("[OUT] user left roulette:", chatID)
    if ok && partnerID != 0 {
        fmt.Println("[OUT] partner removed from roulette:", partnerID)
        logChatEnded(fmt.Sprint(chatID), fmt.Sprint(partnerID))
        logChatEnded(fmt.Sprint(partnerID), fmt.Sprint(chatID))
    }
    //fmt.Println("[QUEUE]", rouletteQueue)
    //fmt.Println("[ACTIVE_CHATS]", activeChats)

    // ===== МЕНЮ =====
    sendMainMenu(ctx, api, chatID)
    if ok && partnerID != 0 {
        sendMainMenu(ctx, api, partnerID)
    }
}



func uniqueQueue(queue []int64) []int64 {
    m := make(map[int64]bool)
    res := []int64{}

    for _, id := range queue {
        if !m[id] {
            m[id] = true
            res = append(res, id)
        }
    }
    return res
}
























// ================== УДАЛЕНИЕ ИЗ ОЧЕРЕДИ ==================
func removeFromQueue(queue []int64, userID int64) []int64 {
	newQueue := []int64{}
	for _, id := range queue {
		if id != userID {
			newQueue = append(newQueue, id)
		}
	}
	return newQueue
}


func sendSearchingMessage(ctx context.Context, api *maxbot.Api, chatID int64) {
    msg := maxbot.NewMessage().
        SetChat(chatID).
        SetText("🔎 Ищем собеседника...")

    // Клавиатура с кнопкой "⏹ Выйти из чата"
    keyboard := api.Messages.NewKeyboardBuilder()
    keyboard.AddRow().
        AddCallback("⏹ Выйти из чата", schemes.DEFAULT, "roulette_out")

    msg.AddKeyboard(keyboard)

    if err := api.Messages.Send(ctx, msg); err != nil {
        fmt.Println("Ошибка отправки сообщения поиска:", err)
    }
}














// ================== ТАЙМЕР ЧАТА ==================
func chatTimer(api *maxbot.Api, u1, u2 int64) {
    timerSeconds := GetChatTimer()
    time.Sleep(time.Duration(timerSeconds) * time.Second)

    mu.Lock()
    defer mu.Unlock()

    if activeChats[u1] != u2 {
        return
    }

    p1 := users[u1]
    p2 := users[u2]
    if p1 == nil || p2 == nil {
        return
    }

    if p1.IsVIP || p2.IsVIP {
        return
    }

    delete(activeChats, u1)
    delete(activeChats, u2)

    minutesStr := fmt.Sprintf("%.0f", float64(timerSeconds)/60)

    msg1 := fmt.Sprintf("⏳ Бесплатные %s минут закончились!\n\n💬 %s всё ещё онлайн...\nНе упусти шанс продолжить разговор 🔥\n\n💎 Активируй VIP и общайся без ограничений:", minutesStr, p2.Name)
    msg2 := fmt.Sprintf("⏳ Бесплатные %s минут закончились!\n\n💬 %s всё ещё онлайн...\nНе упусти шанс продолжить разговор 🔥\n\n💎 Активируй VIP и общайся без ограничений:", minutesStr, p1.Name)

    keyboard := api.Messages.NewKeyboardBuilder()
    keyboard.AddRow().AddCallback("💎 Продолжить без ограничений", schemes.DEFAULT, "vip")
    keyboard.AddRow().AddCallback("🔄 Найти нового собеседника", schemes.DEFAULT, "roulette_in")
    keyboard.AddRow().AddCallback("📩 Пригласить друга 🎁", schemes.DEFAULT, "invite")

    if _, ok := users[u1]; ok {
        msg := maxbot.NewMessage().SetChat(u1).SetText(msg1).AddKeyboard(keyboard)
        _ = api.Messages.Send(context.Background(), msg)
    }
    if _, ok := users[u2]; ok {
        msg := maxbot.NewMessage().SetChat(u2).SetText(msg2).AddKeyboard(keyboard)
        _ = api.Messages.Send(context.Background(), msg)
    }
}




















/*
func autoConnectUsers(ctx context.Context, api *maxbot.Api, userID1, userID2 int64) {
    mu.Lock()
    defer mu.Unlock()

    // ===== Гарантия профиля первого пользователя =====
    p1, ok := users[userID1]
    if !ok || p1 == nil {
        dbProfile, err := loadProfileFromDB(fmt.Sprintf("%d", userID1))
        if err != nil || dbProfile == nil {
            fmt.Println("❌ Профиль первого пользователя не найден")
            return
        }
        users[userID1] = dbProfile
        p1 = dbProfile
    }

    // ===== Гарантия профиля второго пользователя =====
    p2, ok := users[userID2]
    if !ok || p2 == nil {
        dbProfile, err := loadProfileFromDB(fmt.Sprintf("%d", userID2))
        if err != nil || dbProfile == nil {
            fmt.Println("❌ Профиль второго пользователя не найден")
            return
        }
        users[userID2] = dbProfile
        p2 = dbProfile
    }

    // ===== Форсированное соединение, игнорируем фильтры для теста =====
    activeChats[userID1] = userID2
    activeChats[userID2] = userID1

    fmt.Printf("✅ AUTO CONNECT %d ↔ %d\n", userID1, userID2)

    // ===== Показываем профили и кнопку выхода =====
    //leaveKeyboard := api.Messages.NewKeyboardBuilder()
    //leaveKeyboard.AddRow().AddCallback("⏹ Выйти из чата", schemes.DEFAULT, "roulette_out")

    //showProfile(ctx, api, userID1, users[userID2], leaveKeyboard)
    //showProfile(ctx, api, userID2, users[userID1], leaveKeyboard)
}*/