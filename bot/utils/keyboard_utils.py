from typing import List, Tuple, Union
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def build_button(text: str, callback_data: str) -> InlineKeyboardButton:
    """
    Create a standardized inline keyboard button.
    
    Args:
        text: Button text (limited to 30 chars)
        callback_data: Callback data for the button
        
    Returns:
        An InlineKeyboardButton instance
    """
    # Ensure text is not too long (Telegram has limits)
    if len(text) > 30:
        text = text[:27] + "..."
        
    return InlineKeyboardButton(text=text, callback_data=callback_data)

def build_keyboard(buttons: List[Union[InlineKeyboardButton, List[InlineKeyboardButton]]]) -> InlineKeyboardMarkup:
    """
    Build an inline keyboard markup from buttons.
    
    Args:
        buttons: List of buttons or list of button rows
        
    Returns:
        InlineKeyboardMarkup instance
    """
    # If the first item is a button, not a list, wrap in a list for one row
    if buttons and not isinstance(buttons[0], list):
        buttons = [buttons]
        
    return InlineKeyboardMarkup(buttons)

def build_menu(
    buttons: List[InlineKeyboardButton],
    n_cols: int = 2,
    header_buttons: List[InlineKeyboardButton] = None,
    footer_buttons: List[InlineKeyboardButton] = None
) -> InlineKeyboardMarkup:
    """
    Build a menu with a grid of buttons.
    
    Args:
        buttons: List of buttons to arrange in grid
        n_cols: Number of columns in the grid
        header_buttons: Optional buttons to place at the top
        footer_buttons: Optional buttons to place at the bottom
        
    Returns:
        InlineKeyboardMarkup with buttons arranged in a grid
    """
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    
    if header_buttons:
        menu.insert(0, header_buttons)
    
    if footer_buttons:
        menu.append(footer_buttons)
        
    return InlineKeyboardMarkup(menu)

def yes_no_keyboard(yes_data: str = "yes", no_data: str = "no") -> InlineKeyboardMarkup:
    """
    Create a Yes/No keyboard.
    
    Args:
        yes_data: Callback data for 'Yes' button
        no_data: Callback data for 'No' button
        
    Returns:
        InlineKeyboardMarkup with Yes and No buttons
    """
    buttons = [
        build_button("Yes", yes_data),
        build_button("No", no_data)
    ]
    
    return build_keyboard([buttons])

def back_button(callback_data: str = "back") -> List[InlineKeyboardButton]:
    """
    Create a back button row.
    
    Args:
        callback_data: Callback data for the back button
        
    Returns:
        List containing a single back button
    """
    return [build_button("« Back", callback_data)] 