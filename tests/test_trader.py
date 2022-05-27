import pytest
import datetime
import loguru
from pytest_mock import MockerFixture
import shioaji as sj

from decimal import Decimal
from dataclasses import dataclass
from sjtrade.trader import SJTrader
from shioaji.constant import (
    Action,
    TFTStockPriceType,
    TFTOrderType,
    QuoteVersion,
    Exchange,
    OrderState,
    TFTStockOrderLot,
    StockOrderCond,
)


@dataclass
class TickSTKv1:
    code: str
    datetime: datetime.datetime
    close: Decimal
    simtrade: bool


@pytest.fixture
def sjtrader(api: sj.Shioaji) -> SJTrader:
    return SJTrader(api)


@pytest.fixture
def positions():
    return {"1605": -1, "6290": -3, "0000": 3}


@pytest.fixture
def sjtrader_entryed(sjtrader: SJTrader, positions: dict):
    sjtrader.api.place_order.side_effect = lambda contract, order: (
        sj.order.Trade(
            contract,
            order,
            sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        )
    )
    res = sjtrader.place_entry_order(positions, 1.05)
    return sjtrader


def test_sjtrader(api: sj.Shioaji):
    sjtrader = SJTrader(api)
    assert hasattr(sjtrader, "api")
    sjtrader.stop_profit_pct = 0.1
    assert sjtrader.stop_profit_pct == 0.1
    sjtrader.stop_loss_pct = 0.1
    assert sjtrader.stop_loss_pct == 0.1
    sjtrader.position_filepath = "pos.txt"
    assert sjtrader.position_filepath == "pos.txt"


def test_sjtrader_start(sjtrader: SJTrader):
    sjtrader.start()


def test_sjtrader_place_entry_order(
    sjtrader: SJTrader, logger: loguru._logger.Logger, positions: dict
):
    sjtrader.api.place_order.side_effect = lambda contract, order: sj.order.Trade(
        contract, order, sj.order.OrderStatus(status=sj.order.Status.PreSubmitted)
    )
    sjtrader.stop_loss_pct = 0.085
    sjtrader.stop_profit_pct = 0.09
    res = sjtrader.place_entry_order(positions, 1.05)
    logger.warning.assert_called_once()
    sjtrader.api.quote.subscribe.assert_has_calls(
        [
            ((sjtrader.api.Contracts.Stocks["1605"],), dict(version=QuoteVersion.v1)),
            ((sjtrader.api.Contracts.Stocks["6290"],), dict(version=QuoteVersion.v1)),
        ]
    )
    sjtrader.api.update_status.assert_called_once()
    expected = [
        sj.order.Trade(
            sjtrader.api.Contracts.Stocks["1605"],
            sj.Order(
                price=41.35,
                quantity=1,
                action=Action.Sell,
                price_type=TFTStockPriceType.LMT,
                order_type=TFTOrderType.ROD,
            ),
            status=sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        ),
        sj.order.Trade(
            sjtrader.api.Contracts.Stocks["6290"],
            sj.Order(
                price=60.1,
                quantity=3,
                action=Action.Sell,
                price_type=TFTStockPriceType.LMT,
                order_type=TFTOrderType.ROD,
            ),
            status=sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        ),
    ]
    assert sjtrader.positions == {
        "1605": dict(
            contract=sjtrader.api.Contracts.Stocks["1605"],
            quantity=-1,
            stop_loss_price=42.7,
            stop_profit_price=35.9,
            cancel_quantity=0,
            entry_quantity=0,
            open_quantity=0,
            cover_quantity=0,
            entry_trades=[
                expected[0],
            ],
            entry_order_quantity=0,
            cover_order_quantity=0,
            lock=sjtrader.positions["1605"]["lock"]
            # cover_trades=[],
        ),
        "6290": dict(
            contract=sjtrader.api.Contracts.Stocks["6290"],
            quantity=-3,
            stop_loss_price=62.1,
            stop_profit_price=52.2,
            cancel_quantity=0,
            entry_quantity=0,
            open_quantity=0,
            cover_quantity=0,
            entry_trades=[
                expected[1],
            ],
            entry_order_quantity=0,
            cover_order_quantity=0,
            lock=sjtrader.positions["6290"]["lock"]
            # cover_trades=[],
        ),
    }
    assert len(res) == 2
    assert res == expected


def test_sjtrader_cancel_preorder_handler(
    sjtrader_entryed: SJTrader, mocker: MockerFixture
):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, True)

    def make_cancel_order_status(trade):
        trade.status.status = sj.order.Status.Cancelled
        trade.status.cancel_quantity = trade.order.quantity

    sjtrader_entryed.update_status = mocker.MagicMock(
        side_effect=make_cancel_order_status
    )

    sjtrader_entryed.cancel_preorder_handler(Exchange.TSE, tick)
    sjtrader_entryed.api.cancel_order.assert_called_once_with(
        sjtrader_entryed.positions["1605"]["entry_trades"][0]
    )
    # TODO need single trade update status interface
    sjtrader_entryed.update_status.assert_called_once_with(
        sjtrader_entryed.positions["1605"]["entry_trades"][0]
    )
    # sjtrader.api._solace.update_status.assert_called()
    assert sjtrader_entryed.positions["1605"]["cancel_quantity"] == -1


def test_sjtrader_re_entry_order(
    sjtrader_entryed: SJTrader,
    mocker: MockerFixture,
):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, True)

    def make_cancel_order_status(trade):
        trade.status.status = sj.order.Status.Cancelled
        trade.status.cancel_quantity = trade.order.quantity

    sjtrader_entryed.update_status = mocker.MagicMock(
        side_effect=make_cancel_order_status
    )

    sjtrader_entryed.cancel_preorder_handler(Exchange.TSE, tick)

    tick = TickSTKv1("1605", "2022-05-25 09:00:01", 35, False)
    sjtrader_entryed.re_entry_order(Exchange.TSE, tick)
    sjtrader_entryed.api.place_order.assert_called_with(
        contract=sjtrader_entryed.positions["1605"]["contract"],
        order=sj.order.TFTStockOrder(
            price=0,
            quantity=1,
            action=Action.Sell,
            price_type=TFTStockPriceType.MKT,
            order_type=TFTOrderType.ROD,
        ),
    )


def test_sjtrader_stop_profit(sjtrader_entryed: SJTrader, mocker: MockerFixture):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 35.5, False)
    position = sjtrader_entryed.positions["1605"]
    position["open_quantity"] = -1
    sjtrader_entryed.place_cover_order = mocker.MagicMock()
    sjtrader_entryed.stop_profit(position, tick)
    sjtrader_entryed.place_cover_order.assert_called_once()


def test_sjtrader_stop_loss(sjtrader_entryed: SJTrader, mocker: MockerFixture):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, False)
    position = sjtrader_entryed.positions["1605"]
    position["open_quantity"] = -1
    sjtrader_entryed.place_cover_order = mocker.MagicMock()
    sjtrader_entryed.stop_loss(position, tick)
    sjtrader_entryed.place_cover_order.assert_called_once()


def test_sjtrader_intraday_handler(sjtrader_entryed: SJTrader, mocker: MockerFixture):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, True)
    sjtrader_entryed.stop_profit = mocker.MagicMock()
    sjtrader_entryed.stop_loss = mocker.MagicMock()
    sjtrader_entryed.intraday_handler(Exchange.TSE, tick)
    sjtrader_entryed.stop_profit.assert_called_once()
    sjtrader_entryed.stop_loss.assert_called_once()


def test_sjtrader_place_cover_order(sjtrader_entryed: SJTrader):
    position = sjtrader_entryed.positions["1605"]
    position["open_quantity"] = -1
    sjtrader_entryed.place_cover_order(position)
    # TODO assert


def test_sjtrader_open_position_cover(sjtrader: SJTrader):
    sjtrader.open_position_cover()


@pytest.fixture
def order_msg():
    return {
        "operation": {"op_type": "New", "op_code": "00", "op_msg": ""},
        "order": {
            "id": "c21b876d",
            "seqno": "429832",
            "ordno": "W2892",
            "action": "Sell",
            "price": 44.3,
            "quantity": 1,
            "order_cond": "Cash",
            "order_lot": "Common",
            "custom_field": "test",
            "order_type": "ROD",
            "price_type": "LMT",
        },
        "status": {
            "id": "c21b876d",
            "exchange_ts": 1583828972,
            "modified_price": 0,
            "cancel_quantity": 0,
            "web_id": "137",
        },
        "contract": {
            "security_type": "STK",
            "exchange": "TSE",
            "code": "1605",
            "symbol": "",
            "name": "",
            "currency": "TWD",
        },
    }


@pytest.fixture
def deal_msg():
    return {
        "trade_id": "12ab3456",
        "exchange_seq": "123456",
        "broker_id": "your_broker_id",
        "account_id": "your_account_id",
        "action": Action.Buy,
        "code": "1605",
        "order_cond": StockOrderCond.Cash,
        "order_lot": TFTStockOrderLot.Common,
        "price": 12,
        "quantity": 10,
        "web_id": "137",
        "custom_field": "test",
        "ts": 1583828972,
    }


def test_sjtrader_order_deal_handler_receive_order_msg(
    sjtrader_entryed: SJTrader, order_msg: dict, mocker: MockerFixture
):
    sjtrader_entryed.order_handler = mocker.MagicMock()
    sjtrader_entryed.order_deal_handler(OrderState.TFTOrder, order_msg)
    sjtrader_entryed.order_handler.assert_called_once_with(
        order_msg,
        sjtrader_entryed.positions["1605"],
    )


def test_sjtrader_order_deal_handler_receive_deal_msg(
    sjtrader_entryed: SJTrader, deal_msg: dict, mocker: MockerFixture
):
    sjtrader_entryed.deal_handler = mocker.MagicMock()
    sjtrader_entryed.order_deal_handler(OrderState.TFTDeal, deal_msg)
    sjtrader_entryed.deal_handler.assert_called_once_with(
        deal_msg,
        sjtrader_entryed.positions["1605"],
    )


def test_sjtrader_order_handler(sjtrader_entryed: SJTrader, order_msg: dict):
    sjtrader_entryed.order_handler(order_msg, sjtrader_entryed.positions["1605"])


def test_sjtrader_deal_handler(sjtrader_entryed: SJTrader, deal_msg: dict):
    sjtrader_entryed.deal_handler(deal_msg, sjtrader_entryed.positions["1605"])


def test_sjtrader_update_status(sjtrader_entryed: SJTrader):

    sjtrader_entryed.update_status(
        sjtrader_entryed.positions["1605"]["entry_trades"][0]
    )

    sjtrader_entryed.api._solace.update_status.assert_called_with(
        sjtrader_entryed.positions["1605"]["entry_trades"][0].order.account, seqno=""
    )
