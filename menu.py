"""
menu.py
=======
Menu interactivo de terminal para operar el proyecto sin tener que
recordar los comandos de cada modulo por separado.

Uso:
    python menu.py
"""

from llm.consultas import responder_pregunta

PREGUNTAS_SUGERIDAS = [
    "Cual es la ciudad con peor calidad del aire ahora mismo?",
    "Que ciudades superan un AQI de 100?",
    "Como esta el clima en Ciudad de Panama?",
    "Cual ciudad tiene el PM2.5 mas alto?",
]


def menu_pipeline():
    """Submenu para correr el pipeline: una vez, o en modo programado."""
    while True:
        print("\n=== Pipeline de Datos ===")
        print("1. Ejecutar una vez (recomendado para pruebas)")
        print("2. Ejecutar cada hora (modo programado, corre indefinidamente)")
        print("3. Volver al menu principal")
        opcion = input("Selecciona una opcion: ").strip()

        if opcion == "1":
            from pipeline.actualizar import ejecutar_pipeline
            print("\nEjecutando el pipeline una sola vez...\n")
            ejecutar_pipeline()

        elif opcion == "2":
            import time
            import schedule
            from pipeline.actualizar import ejecutar_pipeline
            print("\nModo programado: se ejecuta ahora y luego cada hora.")
            print("Presiona Ctrl+C para detenerlo y volver al menu.\n")
            ejecutar_pipeline()
            schedule.every(1).hours.do(ejecutar_pipeline)
            try:
                while True:
                    schedule.run_pending()
                    time.sleep(60)
            except KeyboardInterrupt:
                print("\nModo programado detenido.")

        elif opcion == "3":
            return
        else:
            print("Opcion invalida, intenta de nuevo.")


def menu_llm():
    """Submenu de preguntas en lenguaje natural al LLM sobre los datos."""
    print("\n=== Consultas al LLM ===")
    print("Escribe tu pregunta sobre calidad del aire o clima.")
    print("Escribe 'salir' para volver al menu principal.\n")
    print("Ejemplos de preguntas que puedes hacer:")
    for ejemplo in PREGUNTAS_SUGERIDAS:
        print(f"  - {ejemplo}")

    historial = []
    while True:
        pregunta = input("\nTu pregunta: ").strip()
        if pregunta.lower() in ("salir", "exit", "volver"):
            return
        if not pregunta:
            continue

        respuesta = responder_pregunta(pregunta, historial)
        print(f"\nLLM: {respuesta}")

        # Se guarda el intercambio para dar contexto a la siguiente pregunta.
        historial.append({"role": "user", "content": pregunta})
        historial.append({"role": "assistant", "content": respuesta})
        # Se acota el historial para no mandar mensajes de mas al LLM.
        historial[:] = historial[-8:]


def menu_principal():
    """Punto de entrada: muestra el menu principal en bucle."""
    while True:
        print("\n" + "=" * 50)
        print("Monitor de Calidad del Aire - Menu Principal")
        print("=" * 50)
        print("1. Pipeline de datos")
        print("2. Exportar a Power BI")
        print("3. Entrenar clasificador")
        print("4. Consultar con LLM (preguntas en lenguaje natural)")
        print("5. Salir")
        opcion = input("Selecciona una opcion: ").strip()

        if opcion == "1":
            menu_pipeline()

        elif opcion == "2":
            from exportar_powerbi import main as exportar_main
            exportar_main()

        elif opcion == "3":
            from models.clasificador import entrenar_clasificador
            entrenar_clasificador()

        elif opcion == "4":
            menu_llm()

        elif opcion == "5":
            print("Hasta luego.")
            break

        else:
            print("Opcion invalida, intenta de nuevo.")


if __name__ == "__main__":
    menu_principal()
