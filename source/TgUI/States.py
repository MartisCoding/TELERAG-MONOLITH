from aiogram.fsm.state import State, StatesGroup


class AddSourceStates(StatesGroup):
    waiting_for_source = State()

class ProcessingResponseStates(StatesGroup):
    waiting_for_processing = State()