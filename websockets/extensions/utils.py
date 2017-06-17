__all__ = ['parse_extensions']


def unquote_value(value):
    if value and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def parse_extensions(header):
    """
    Parse an extension header and return a list of extension/parameters
    :param header: str
    :return: [('extension name', {parameters dict}), ...]
    """
    extensions = []
    header = header.replace('\n', ',')
    for ext_string in header.split(','):
        ext_name, *params_list = ext_string.strip().split(';')
        ext_name = ext_name.strip()
        if not ext_name:
            # Can happen with an initial carriage return
            continue
        parameters = {}
        for param in params_list:
            if '=' in param:
                param, param_value = param.split('=', 1)
                param_value = unquote_value(param_value.strip())
            else:
                param_value = None
            parameters[param.strip()] = param_value
        extensions.append((ext_name, parameters))
    return extensions
