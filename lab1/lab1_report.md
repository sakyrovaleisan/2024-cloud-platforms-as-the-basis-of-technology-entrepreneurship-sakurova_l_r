# Laboratory Work Report

**University:** [ITMO University](https://itmo.ru/ru/)  
**Faculty:** [FICT](https://fict.itmo.ru)  
**Course:** Облачные платформы как основа технологического предпринимательства
**Year:** 2025/2026  
**Group:** U4225  
**Author:** Sakurova Leisan  
**Lab:** Lab1  
**Date of create:** 01.12.2025  
**Date of finished:** 01.12.2025  

---
## Лабораторная работа №1 "Обзор Google Cloud и исследование основных сервисов."
## 📘 Цель работы
Ознакомиться с основными возможностями и преимуществами облачной платформы Google Cloud.

## 🧠 Ход выполнения
### 1. Получение доступа к Google Cloud
Заполнилf форму, указав свой Gmail для получения доступа к Google Cloud Platform.
### 2. Создание сервисного аккаунта
Во вкладке IAM создала сервисный аккаунт с ролью Storage Admin.
<img width="1398" height="717" alt="image" src="https://github.com/user-attachments/assets/47ce4778-b636-4bbe-99e4-5072b8837df6" />
<img width="1402" height="713" alt="image" src="https://github.com/user-attachments/assets/ac1730c3-485d-447e-8c86-5568ababf4da" />

### Создание виртуальной машины (Compute Engine)
Я развернула виртуальную машину, которая будет выполнять операции с хранилищем, используя удостоверение SA.
<img width="1402" height="717" alt="image" src="https://github.com/user-attachments/assets/5d802811-706e-4be6-aa27-9f3373fbed64" />
<img width="1405" height="713" alt="image" src="https://github.com/user-attachments/assets/4e591973-ac7c-4d91-9396-8e42f1e8f2e5" />

### Подключилась к VM через SSH и выполнила через команду gsutil копирование файлов на мою VM.
С помощью утилиты gsutils нашла бакет lab1-bucket-itmo и скопировала 3 файла в локальную папку на VM. Использовала команду ls -lah 
<img width="896" height="653" alt="image" src="https://github.com/user-attachments/assets/637165aa-9f69-48b2-8f07-9a29af0ceff7" />

Удалила за собой все созданные сервисы.
<img width="857" height="687" alt="image" src="https://github.com/user-attachments/assets/cd6dbf1c-1a77-4593-83f2-87d933b7580e" />
<img width="939" height="554" alt="image" src="https://github.com/user-attachments/assets/a5bc02af-1582-4e4d-93a3-d69ffafa9497" />

