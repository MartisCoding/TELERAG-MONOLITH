from dataclasses import dataclass, field, make_dataclass, is_dataclass
from typing import Any, Optional

class CoreConfig:

    _instance: Optional['CoreConfig'] = None

    @classmethod
    def get_instance(cls) -> 'CoreConfig':
        if cls._instance is None:
            raise ValueError("CoreConfig instance not created. Use get_config() to create an instance.")
        return cls._instance

    def __init__(self, file: str, file_extension: str):
        self._instance = self
        self.file = file
        self.file_extension = file_extension
        self._data = ""

    def get_data(self, name: str):
        with open(self.file, "r") as file:
            self._data = file.read()

        config = self.get_dict()
        config_dataclass = self._json_to_dataclass(name, config)
        if not is_dataclass(config_dataclass):
            raise ValueError(f"Invalid dataclass: {config_dataclass}")
        return config_dataclass
    def get_dict(self):
        if self.file_extension == ".json":
            return self._parse_json()
        elif self.file_extension == ".yaml":
            return self._parse_yaml()
        elif self.file_extension == ".toml":
            return self._parse_toml()
        elif self.file_extension == ".xml":
            return self._parse_xml()
        else:
            raise ValueError(f"Unsupported file extension: {self.file_extension}")

    def _parse_json(self):
        import json
        data = json.loads(self._data)
        return data

    def _parse_yaml(self):
        import yaml
        data = yaml.safe_load(self._data)
        return data

    def _parse_toml(self):
        import tomllib
        data = tomllib.loads(self._data)
        return data

    def _parse_xml(self):
        import xml.etree.ElementTree as et
        root = et.fromstring(self._data)
        data = {}
        for child in root:
            data[child.tag] = child.text
        return data

    @staticmethod
    def _json_to_dataclass(name: str, data: dict):
        fields = []

        for key, value in data.items():
            if isinstance(value, dict):
                nested_cls = CoreConfig._json_to_dataclass(key.capitalize(), value)
                fields.append(
                    (key, nested_cls, field(default_factory=lambda v=value: CoreConfig._json_to_dataclass(key.capitalize(), v))))
            elif isinstance(value, list):
                if value and isinstance(value[0], dict):
                    nested_cls = CoreConfig._json_to_dataclass(key.capitalize(), value[0])
                    fields.append((key, list[nested_cls], field(
                        default_factory=lambda v=value: [CoreConfig._json_to_dataclass(key.capitalize(), i) for i in v])))
                else:
                    elem_type = type(value[0]) if value else Any
                    fields.append((key, list[elem_type], field(default=value)))
            else:
                fields.append((key, type(value), field(default=value)))

        return make_dataclass(name, fields)

@dataclass


def get_config(file: str, file_extension: str, name: str):
    config = CoreConfig(file, file_extension)
    config_data = config.get_data(name)
    return config_data

def update_config(config: Any):
    """
    Fetches the latest configuration from the config file and updates the dataclass instance.
    """
    config_instance = CoreConfig.get_instance()
    config_data = config_instance.get_data(config.__class__.__name__)
    del config
    return config_data




