# Кастомний клас винятку для "сутність не знайдена"
class EntityNotFoundException(Exception):
    def __init__(self, entity_name: str, entity_id: int):
        self.entity_name = entity_name
        self.entity_id = entity_id
        self.message = f"{entity_name} з ID {entity_id} не знайдено"
        super().__init__(self.message)