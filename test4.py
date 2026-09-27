from __future__ import annotations

import sys
from enum import Enum
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Палитра
# ---------------------------------------------------------------------------
COLOR_BG = "#2b2b2b"
COLOR_CARD = "#333333"
COLOR_BORDER = "#5a5a5a"
COLOR_DIVIDER = "#454545"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_MUTED = "#a0a0a0"
COLOR_TEXT_DIM = "#707070"

COLOR_SQUARE_LIGHT = "#d9c9a8"
COLOR_SQUARE_DARK = "#7a5a3a"
COLOR_HIGHLIGHT_SELECT = "#22c55e"
COLOR_HIGHLIGHT_MOVE = "#3b82f6"
COLOR_HIGHLIGHT_CAPTURE = "#dc2626"
COLOR_HIGHLIGHT_LAST = "#f59e0b"
COLOR_CHECK = "#ef4444"

COLOR_WHITE_FIG = "#f5f5f5"
COLOR_BLACK_FIG = "#1a1a1a"
COLOR_WHITE_OUTLINE = "#333333"
COLOR_BLACK_OUTLINE = "#cccccc"

COLOR_STATUS_BG = "#1a1a1a"
COLOR_ACCENT = "#22c55e"


# ---------------------------------------------------------------------------
# Модель
# ---------------------------------------------------------------------------
class PieceColor(Enum):
    WHITE = "white"
    BLACK = "black"


class PieceType(Enum):
    PAWN = "pawn"
    KNIGHT = "knight"
    BISHOP = "bishop"
    ROOK = "rook"
    QUEEN = "queen"
    KING = "king"


class Piece:
    __slots__ = ("color", "ptype")

    def __init__(self, color: PieceColor, ptype: PieceType) -> None:
        self.color = color
        self.ptype = ptype

    def __repr__(self) -> str:
        return f"<{self.color.value} {self.ptype.value}>"

    def symbol(self) -> str:
        table = {
            (PieceColor.WHITE, PieceType.KING): "♔",
            (PieceColor.WHITE, PieceType.QUEEN): "♕",
            (PieceColor.WHITE, PieceType.ROOK): "♖",
            (PieceColor.WHITE, PieceType.BISHOP): "♗",
            (PieceColor.WHITE, PieceType.KNIGHT): "♘",
            (PieceColor.WHITE, PieceType.PAWN): "♙",
            (PieceColor.BLACK, PieceType.KING): "♚",
            (PieceColor.BLACK, PieceType.QUEEN): "♛",
            (PieceColor.BLACK, PieceType.ROOK): "♜",
            (PieceColor.BLACK, PieceType.BISHOP): "♝",
            (PieceColor.BLACK, PieceType.KNIGHT): "♞",
            (PieceColor.BLACK, PieceType.PAWN): "♟",
        }
        return table[(self.color, self.ptype)]


# ---------------------------------------------------------------------------
# Логика игры
# ---------------------------------------------------------------------------
class ChessGame:
    """Минимальная, но рабочая логика шахмат."""

    def __init__(self) -> None:
        self.board: List[List[Optional[Piece]]] = [
            [None] * 8 for _ in range(8)
        ]
        self.turn: PieceColor = PieceColor.WHITE
        self.selected: Optional[Tuple[int, int]] = None
        self.legal_moves: List[Tuple[int, int]] = []
        self.last_move: Optional[Tuple[Tuple[int, int],
                                        Tuple[int, int]]] = None
        self.en_passant_target: Optional[Tuple[int, int]] = None
        self.castling_rights = {
            PieceColor.WHITE: {"K": True, "Q": True},
            PieceColor.BLACK: {"K": True, "Q": True},
        }
        self.game_over = False
        self.status_message = "Ход белых"
        self._setup_initial_position()

    # -------------------------------------------------- расстановка
    def _setup_initial_position(self) -> None:
        back_rank = [
            PieceType.ROOK, PieceType.KNIGHT, PieceType.BISHOP,
            PieceType.QUEEN, PieceType.KING, PieceType.BISHOP,
            PieceType.KNIGHT, PieceType.ROOK,
        ]
        for col in range(8):
            self.board[0][col] = Piece(PieceColor.BLACK, back_rank[col])
            self.board[1][col] = Piece(PieceColor.BLACK, PieceType.PAWN)
            self.board[6][col] = Piece(PieceColor.WHITE, PieceType.PAWN)
            self.board[7][col] = Piece(PieceColor.WHITE, back_rank[col])

    def reset(self) -> None:
        self.__init__()

    # -------------------------------------------------- помощники
    @staticmethod
    def inside(row: int, col: int) -> bool:
        return 0 <= row < 8 and 0 <= col < 8

    def piece_at(self, row: int, col: int) -> Optional[Piece]:
        if not self.inside(row, col):
            return None
        return self.board[row][col]

    def find_king(self, color: PieceColor) -> Optional[Tuple[int, int]]:
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p and p.color == color and p.ptype == PieceType.KING:
                    return (r, c)
        return None

    @staticmethod
    def _opponent(color: PieceColor) -> PieceColor:
        return PieceColor.BLACK if color == PieceColor.WHITE else PieceColor.WHITE

    # -------------------------------------------------- генерация ходов
    def _pseudo_moves(self, row: int, col: int,
                      for_attack: bool = False) -> List[Tuple[int, int]]:
        """
        Псевдо-легальные ходы (без проверки, оставляет ли ход короля под шахом).

        for_attack=True — используется из _is_attacked. В этом режиме
        НЕ генерируются рокировки и НЕ вызывается _is_attacked, иначе
        получается бесконечная рекурсия.
        """
        piece = self.board[row][col]
        if piece is None:
            return []

        color = piece.color
        moves: List[Tuple[int, int]] = []

        def add(r: int, c: int) -> None:
            if not self.inside(r, c):
                return
            target = self.board[r][c]
            if target is None or target.color != color:
                moves.append((r, c))

        def slide(dirs):
            for dr, dc in dirs:
                r, c = row + dr, col + dc
                while self.inside(r, c):
                    target = self.board[r][c]
                    if target is None:
                        moves.append((r, c))
                    else:
                        if target.color != color:
                            moves.append((r, c))
                        break
                    r += dr
                    c += dc

        if piece.ptype == PieceType.PAWN:
            direction = -1 if color == PieceColor.WHITE else 1
            start_row = 6 if color == PieceColor.WHITE else 1

            r1 = row + direction
            if self.inside(r1, col) and self.board[r1][col] is None:
                moves.append((r1, col))
                r2 = row + 2 * direction
                if row == start_row and self.board[r2][col] is None:
                    moves.append((r2, col))

            for dc in (-1, 1):
                r = row + direction
                c = col + dc
                if self.inside(r, c):
                    target = self.board[r][c]
                    if target and target.color != color:
                        moves.append((r, c))
                    if (self.en_passant_target == (r, c)
                            and target is None):
                        moves.append((r, c))

        elif piece.ptype == PieceType.KNIGHT:
            for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                           (1, -2), (1, 2), (2, -1), (2, 1)):
                add(row + dr, col + dc)

        elif piece.ptype == PieceType.BISHOP:
            slide(((-1, -1), (-1, 1), (1, -1), (1, 1)))

        elif piece.ptype == PieceType.ROOK:
            slide(((-1, 0), (1, 0), (0, -1), (0, 1)))

        elif piece.ptype == PieceType.QUEEN:
            slide(((-1, -1), (-1, 1), (1, -1), (1, 1),
                   (-1, 0), (1, 0), (0, -1), (0, 1)))

        elif piece.ptype == PieceType.KING:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    add(row + dr, col + dc)

            # Рокировка — только при обычной генерации.
            if for_attack:
                return moves

            rights = self.castling_rights[color]
            home_row = 7 if color == PieceColor.WHITE else 0
            if row == home_row and col == 4 and not self._is_attacked(
                    row, col, self._opponent(color)):
                # короткая
                if rights["K"]:
                    if (self.board[home_row][5] is None
                            and self.board[home_row][6] is None
                            and self.board[home_row][7]
                            and self.board[home_row][7].ptype == PieceType.ROOK):
                        if not self._is_attacked(home_row, 5,
                                                 self._opponent(color)):
                            moves.append((home_row, 6))
                # длинная
                if rights["Q"]:
                    if (self.board[home_row][3] is None
                            and self.board[home_row][2] is None
                            and self.board[home_row][1] is None
                            and self.board[home_row][0]
                            and self.board[home_row][0].ptype == PieceType.ROOK):
                        if not self._is_attacked(home_row, 3,
                                                 self._opponent(color)):
                            moves.append((home_row, 2))

        return moves

    def _is_attacked(self, row: int, col: int,
                     by_color: PieceColor) -> bool:
        """Атаковано ли поле (row, col) фигурами цвета by_color."""
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p is None or p.color != by_color:
                    continue
                if p.ptype == PieceType.PAWN:
                    direction = -1 if p.color == PieceColor.WHITE else 1
                    if r + direction == row and abs(c - col) == 1:
                        return True
                    continue
                # for_attack=True — отключает рокировку и рекурсию
                if (row, col) in self._pseudo_moves(r, c, for_attack=True):
                    return True
        return False

    def _king_in_check(self, color: PieceColor) -> bool:
        pos = self.find_king(color)
        if pos is None:
            return False
        return self._is_attacked(pos[0], pos[1], self._opponent(color))

    def legal_moves_from(self, row: int, col: int) -> List[Tuple[int, int]]:
        piece = self.board[row][col]
        if piece is None:
            return []
        result = []
        for r, c in self._pseudo_moves(row, col):
            if self._move_leaves_king_safe(row, col, r, c, piece.color):
                result.append((r, c))
        return result

    def _move_leaves_king_safe(self, r0: int, c0: int,
                               r1: int, c1: int,
                               color: PieceColor) -> bool:
        saved_from = self.board[r0][c0]
        saved_to = self.board[r1][c1]
        ep_saved = None
        if (saved_from and saved_from.ptype == PieceType.PAWN
                and self.en_passant_target == (r1, c1)
                and saved_to is None):
            ep_row = r0
            ep_saved = self.board[ep_row][c1]
            self.board[ep_row][c1] = None

        self.board[r1][c1] = saved_from
        self.board[r0][c0] = None
        in_check = self._king_in_check(color)
        self.board[r0][c0] = saved_from
        self.board[r1][c1] = saved_to
        if ep_saved is not None:
            self.board[r0][c1] = ep_saved
        return not in_check

    def has_any_legal_move(self, color: PieceColor) -> bool:
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p and p.color == color:
                    if self.legal_moves_from(r, c):
                        return True
        return False

    # -------------------------------------------------- ход
    def select(self, row: int, col: int) -> None:
        if self.game_over:
            return
        piece = self.board[row][col]

        if self.selected == (row, col):
            self.selected = None
            self.legal_moves = []
            return

        if self.selected is not None and (row, col) in self.legal_moves:
            self._make_move(self.selected, (row, col))
            return

        if piece is not None and piece.color == self.turn:
            self.selected = (row, col)
            self.legal_moves = self.legal_moves_from(row, col)
        else:
            self.selected = None
            self.legal_moves = []

    def _make_move(self, src: Tuple[int, int],
                   dst: Tuple[int, int]) -> None:
        r0, c0 = src
        r1, c1 = dst
        piece = self.board[r0][c0]
        assert piece is not None

        captured = self.board[r1][c1]

        # взятие на проходе
        if (piece.ptype == PieceType.PAWN
                and self.en_passant_target == (r1, c1)
                and captured is None):
            ep_row = r0
            self.board[ep_row][c1] = None

        # рокировка
        if piece.ptype == PieceType.KING and abs(c1 - c0) == 2:
            home_row = r0
            if c1 > c0:
                self.board[home_row][5] = self.board[home_row][7]
                self.board[home_row][7] = None
            else:
                self.board[home_row][3] = self.board[home_row][0]
                self.board[home_row][0] = None

        # сам ход
        self.board[r1][c1] = piece
        self.board[r0][c0] = None

        # обновляем права рокировки
        if piece.ptype == PieceType.KING:
            self.castling_rights[piece.color]["K"] = False
            self.castling_rights[piece.color]["Q"] = False
        if piece.ptype == PieceType.ROOK:
            home_row = 7 if piece.color == PieceColor.WHITE else 0
            if r0 == home_row and c0 == 0:
                self.castling_rights[piece.color]["Q"] = False
            if r0 == home_row and c0 == 7:
                self.castling_rights[piece.color]["K"] = False

        # обновляем en passant
        self.en_passant_target = None
        if piece.ptype == PieceType.PAWN and abs(r1 - r0) == 2:
            self.en_passant_target = ((r0 + r1) // 2, c0)

        # превращение пешки (для демо — в ферзя)
        promo_row = 0 if piece.color == PieceColor.WHITE else 7
        if piece.ptype == PieceType.PAWN and r1 == promo_row:
            self.board[r1][c1] = Piece(piece.color, PieceType.QUEEN)

        self.last_move = (src, dst)
        self.selected = None
        self.legal_moves = []

        # смена хода
        self.turn = self._opponent(self.turn)
        self._update_status()

    def _update_status(self) -> None:
        color_name = "белых" if self.turn == PieceColor.WHITE else "чёрных"
        in_check = self._king_in_check(self.turn)
        has_moves = self.has_any_legal_move(self.turn)

        if in_check and not has_moves:
            winner = "чёрные" if self.turn == PieceColor.WHITE else "белые"
            self.status_message = f"МАТ! Победа: {winner}"
            self.game_over = True
        elif not in_check and not has_moves:
            self.status_message = "ПАТ! Ничья"
            self.game_over = True
        elif in_check:
            self.status_message = f"ШАХ! Ход {color_name}"
        else:
            self.status_message = f"Ход {color_name}"


# ---------------------------------------------------------------------------
# Виджет доски
# ---------------------------------------------------------------------------
class ChessBoardWidget(QWidget):
    move_made = Signal(str)

    def __init__(self, game: ChessGame, parent=None) -> None:
        super().__init__(parent)
        self.game = game
        self.setMinimumSize(480, 480)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._hover: Optional[Tuple[int, int]] = None

    # -------------------------------------------------- геометрия
    def _board_rect(self) -> QRectF:
        side = min(self.width(), self.height())
        x = (self.width() - side) / 2
        y = (self.height() - side) / 2
        return QRectF(x, y, side, side)

    def _square_size(self) -> float:
        return self._board_rect().width() / 8

    def _square_at(self, pos: QPointF) -> Optional[Tuple[int, int]]:
        rect = self._board_rect()
        if not rect.contains(pos):
            return None
        sq = self._square_size()
        col = int((pos.x() - rect.left()) / sq)
        row = int((pos.y() - rect.top()) / sq)
        if 0 <= row < 8 and 0 <= col < 8:
            return (row, col)
        return None

    # -------------------------------------------------- события
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        pos = event.position()
        sq = self._square_at(pos)
        if sq is not None:
            self.game.select(*sq)
            self.update()
            self.move_made.emit(self.game.status_message)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        sq = self._square_at(event.position())
        if sq != self._hover:
            self._hover = sq
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = None
        self.update()

    # -------------------------------------------------- отрисовка
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self._board_rect()
        sq = self._square_size()

        # фон
        painter.fillRect(self.rect(), QColor(COLOR_BG))

        # клетки
        for row in range(8):
            for col in range(8):
                x = rect.left() + col * sq
                y = rect.top() + row * sq
                light = (row + col) % 2 == 0
                color = QColor(COLOR_SQUARE_LIGHT if light
                               else COLOR_SQUARE_DARK)
                painter.fillRect(QRectF(x, y, sq, sq), color)

        # подсветка последнего хода
        if self.game.last_move:
            for (r, c) in self.game.last_move:
                x = rect.left() + c * sq
                y = rect.top() + r * sq
                overlay = QColor(COLOR_HIGHLIGHT_LAST)
                overlay.setAlpha(90)
                painter.fillRect(QRectF(x, y, sq, sq), overlay)

        # подсветка шаха
        if not self.game.game_over and self.game._king_in_check(
                self.game.turn):
            king_pos = self.game.find_king(self.game.turn)
            if king_pos:
                r, c = king_pos
                x = rect.left() + c * sq
                y = rect.top() + r * sq
                overlay = QColor(COLOR_CHECK)
                overlay.setAlpha(140)
                painter.fillRect(QRectF(x, y, sq, sq), overlay)

        # выбранная фигура
        if self.game.selected:
            r, c = self.game.selected
            x = rect.left() + c * sq
            y = rect.top() + r * sq
            pen = QPen(QColor(COLOR_HIGHLIGHT_SELECT), 4)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(x + 2, y + 2, sq - 4, sq - 4))

        # легальные ходы
        for (r, c) in self.game.legal_moves:
            x = rect.left() + c * sq
            y = rect.top() + r * sq
            target = self.game.board[r][c]
            is_capture = (target is not None
                          or (self.game.en_passant_target == (r, c)))
            color = QColor(COLOR_HIGHLIGHT_CAPTURE if is_capture
                           else COLOR_HIGHLIGHT_MOVE)
            color.setAlpha(160)
            if is_capture:
                pen = QPen(color, 4)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(
                    QRectF(x + 4, y + 4, sq - 8, sq - 8)
                )
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(
                    QPointF(x + sq / 2, y + sq / 2), sq * 0.14, sq * 0.14
                )

        # hover
        if self._hover and self._hover != self.game.selected:
            r, c = self._hover
            x = rect.left() + c * sq
            y = rect.top() + r * sq
            pen = QPen(QColor(255, 255, 255, 80), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(x + 1, y + 1, sq - 2, sq - 2))

        # фигуры
        font = QFont("DejaVu Sans", int(sq * 0.6))
        font.setBold(True)
        painter.setFont(font)

        for row in range(8):
            for col in range(8):
                piece = self.game.board[row][col]
                if piece is None:
                    continue
                x = rect.left() + col * sq
                y = rect.top() + row * sq
                text_rect = QRectF(x, y, sq, sq)
                if piece.color == PieceColor.WHITE:
                    painter.setPen(QPen(QColor(COLOR_WHITE_OUTLINE), 2))
                    painter.drawText(
                        text_rect.adjusted(1, 1, 1, 1),
                        Qt.AlignCenter, piece.symbol()
                    )
                    painter.setPen(QColor(COLOR_WHITE_FIG))
                else:
                    painter.setPen(QPen(QColor(COLOR_BLACK_OUTLINE), 2))
                    painter.drawText(
                        text_rect.adjusted(1, 1, 1, 1),
                        Qt.AlignCenter, piece.symbol()
                    )
                    painter.setPen(QColor(COLOR_BLACK_FIG))
                painter.drawText(text_rect, Qt.AlignCenter, piece.symbol())

        # координаты
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.setPen(QColor(COLOR_TEXT_MUTED))
        for i in range(8):
            letter = chr(ord('a') + i)
            painter.drawText(
                QRectF(rect.left() + i * sq, rect.bottom() + 2,
                       sq, 20),
                Qt.AlignCenter, letter
            )
            number = str(8 - i)
            painter.drawText(
                QRectF(rect.left() - 22, rect.top() + i * sq,
                       20, sq),
                Qt.AlignCenter, number
            )

        # рамка
        pen = QPen(QColor(COLOR_BORDER), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class ChessApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Демонстрационная шахматная доска")
        self.resize(900, 820)
        self.setMinimumSize(720, 700)

        self.game = ChessGame()

        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)

        self.board_widget = ChessBoardWidget(self.game)
        self.board_widget.move_made.connect(self._on_move)

        side = QFrame()
        side.setObjectName("sidePanel")
        side.setFixedWidth(260)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(16, 16, 16, 16)
        side_layout.setSpacing(12)

        title = QLabel("ИНФОРМАЦИЯ")
        title.setObjectName("panelTitle")
        side_layout.addWidget(title)

        self.lbl_turn = QLabel("Ход белых")
        self.lbl_turn.setObjectName("turnLabel")
        self.lbl_turn.setWordWrap(True)
        side_layout.addWidget(self.lbl_turn)

        self.lbl_state = QLabel("Состояние: игра")
        self.lbl_state.setObjectName("stateLabel")
        side_layout.addWidget(self.lbl_state)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        side_layout.addWidget(divider)

        hint = QLabel(
            "• Клик по фигуре — выбрать\n"
            "• Клик по подсвеченному полю — ход\n"
            "• Зелёная точка — обычный ход\n"
            "• Красный круг — взятие\n"
            "• Оранжевая подсветка — последний ход\n"
            "• Красная подсветка — шах"
        )
        hint.setObjectName("hintText")
        hint.setWordWrap(True)
        side_layout.addWidget(hint)

        side_layout.addStretch(1)

        self.btn_new = QPushButton("НОВАЯ ПАРТИЯ")
        self.btn_new.setObjectName("primaryButton")
        self.btn_new.setMinimumHeight(44)
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.clicked.connect(self._on_new_game)

        self.btn_quit = QPushButton("ВЫХОД")
        self.btn_quit.setObjectName("secondaryButton")
        self.btn_quit.setMinimumHeight(44)
        self.btn_quit.setCursor(Qt.PointingHandCursor)
        self.btn_quit.clicked.connect(self.close)

        side_layout.addWidget(self.btn_new)
        side_layout.addWidget(self.btn_quit)

        content_layout.addWidget(self.board_widget, 1)
        content_layout.addWidget(side)

        root.addWidget(content, 1)
        root.addWidget(self._build_status_bar())

        self._apply_styles()
        self._refresh_status()

    # -------------------------------------------------- верхняя панель
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(60)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("ДЕМОНСТРАЦИОННАЯ ШАХМАТНАЯ ДОСКА")
        title.setObjectName("topBarTitle")

        version = QLabel("v 1.0")
        version.setObjectName("topBarVersion")

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addStretch(1)

        return bar

    # -------------------------------------------------- нижняя панель
    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(30)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)

        self.lbl_status = QLabel("Ход белых")
        self.lbl_status.setObjectName("statusText")

        hints = QLabel("Клик — выбрать / ход")
        hints.setObjectName("statusHints")

        layout.addWidget(self.lbl_status, 1)
        layout.addWidget(hints, 0)

        return bar

    # -------------------------------------------------- обработчики
    def _on_move(self, message: str) -> None:
        self._refresh_status()

    def _on_new_game(self) -> None:
        self.game.reset()
        self.board_widget.update()
        self._refresh_status()

    def _refresh_status(self) -> None:
        msg = self.game.status_message
        self.lbl_status.setText(msg.upper())
        self.lbl_turn.setText(msg)

        if self.game.game_over:
            self.lbl_state.setText("Состояние: партия завершена")
            self.lbl_state.setStyleSheet(
                f"color: {COLOR_HIGHLIGHT_CAPTURE}; "
                f"font-family: Consolas; font-weight: 900; "
                f"font-size: 12pt; background: transparent;"
            )
        elif self.game._king_in_check(self.game.turn):
            self.lbl_state.setText("Состояние: ШАХ")
            self.lbl_state.setStyleSheet(
                f"color: {COLOR_CHECK}; "
                f"font-family: Consolas; font-weight: 900; "
                f"font-size: 12pt; background: transparent;"
            )
        else:
            self.lbl_state.setText("Состояние: игра")
            self.lbl_state.setStyleSheet(
                f"color: {COLOR_TEXT}; "
                f"font-family: Consolas; font-weight: 900; "
                f"font-size: 12pt; background: transparent;"
            )

    # -------------------------------------------------- стили
    def _apply_styles(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, QWidget#root {{
                background: {COLOR_BG};
            }}
            QWidget {{
                color: {COLOR_TEXT};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QLabel {{
                background: transparent;
                color: {COLOR_TEXT};
                font-size: 10pt;
            }}

            QFrame#topBar {{
                background: {COLOR_CARD};
                border-bottom: 2px solid {COLOR_BORDER};
            }}
            QLabel#topBarTitle {{
                font-family: 'Consolas', monospace;
                font-size: 13pt;
                font-weight: 900;
                color: {COLOR_TEXT};
                letter-spacing: 4px;
            }}
            QLabel#topBarVersion {{
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                color: {COLOR_TEXT_MUTED};
                margin-left: 10px;
            }}

            QFrame#sidePanel {{
                background: {COLOR_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
            QLabel#panelTitle {{
                font-family: 'Consolas', monospace;
                font-size: 11pt;
                font-weight: 900;
                color: {COLOR_TEXT_MUTED};
                letter-spacing: 3px;
            }}
            QLabel#turnLabel {{
                font-family: 'Consolas', monospace;
                font-size: 14pt;
                font-weight: 900;
                color: {COLOR_ACCENT};
                letter-spacing: 2px;
            }}
            QLabel#stateLabel {{
                font-family: 'Consolas', monospace;
                font-size: 12pt;
                font-weight: 900;
                color: {COLOR_TEXT};
            }}
            QLabel#hintText {{
                font-family: 'Segoe UI', sans-serif;
                font-size: 10pt;
                color: {COLOR_TEXT_MUTED};
            }}
            QFrame#divider {{
                background: {COLOR_DIVIDER};
                border: none;
            }}

            QPushButton#primaryButton {{
                background: {COLOR_ACCENT};
                color: #0a1f10;
                border: 2px solid {COLOR_ACCENT};
                border-radius: 3px;
                font-family: 'Consolas', monospace;
                font-size: 11pt;
                font-weight: 900;
                letter-spacing: 2px;
            }}
            QPushButton#primaryButton:hover {{
                background: #16a34a;
                border: 2px solid #16a34a;
            }}

            QPushButton#secondaryButton {{
                background: {COLOR_BG};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                border-radius: 3px;
                font-family: 'Consolas', monospace;
                font-size: 11pt;
                font-weight: 900;
                letter-spacing: 2px;
            }}
            QPushButton#secondaryButton:hover {{
                background: #3a3a3a;
                border: 2px solid #707070;
            }}

            QFrame#statusBar {{
                background: {COLOR_STATUS_BG};
                border-top: 1px solid {COLOR_DIVIDER};
            }}
            QLabel#statusText {{
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                font-weight: 900;
                color: {COLOR_TEXT};
                letter-spacing: 1px;
            }}
            QLabel#statusHints {{
                font-family: 'Consolas', monospace;
                font-size: 9pt;
                color: {COLOR_TEXT_DIM};
                letter-spacing: 1px;
            }}

            QToolTip {{
                background: {COLOR_CARD};
                color: {COLOR_TEXT};
                border: 1px solid {COLOR_BORDER};
                padding: 4px;
            }}
        """)


# ---------------------------------------------------------------------------
def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = ChessApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())