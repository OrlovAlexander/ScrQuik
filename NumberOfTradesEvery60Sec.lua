--Вывод сообщения с количеством сделок через каждые 60 секунд
--при наличии подключения к серверу
--<BODY
message("<BODY>", 2)
message("Скрипт запущен.")
--BODY>
	function main()
		message("Уже main()", 2)
		while isConnected() == 1 do
			number_of_trades = getNumberOf("trades")
			message("Общее количество сделок: " .. number_of_trades)
			sleep(60000)
		end
	end
--<BODY
message("Здесь тоже <BODY>", 2)
--BODY>