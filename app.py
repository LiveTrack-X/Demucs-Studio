import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from demucs_gui.ui import main

    raise SystemExit(main())
