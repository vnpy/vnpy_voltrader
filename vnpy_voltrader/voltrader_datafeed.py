from datetime import datetime, timedelta
from collections.abc import Callable

from icetcore import TCoreAPI, BarType

from vnpy.trader.setting import SETTINGS
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, HistoryRequest, TickData
from vnpy.trader.utility import ZoneInfo
from vnpy.trader.datafeed import BaseDatafeed


# 时间周期映射
INTERVAL_VT2ICE: dict[Interval, tuple] = {
    Interval.MINUTE: (BarType.MINUTE, 1),
    Interval.HOUR: (BarType.MINUTE, 60),
    Interval.DAILY: (BarType.DK, 1)
}

# 时间调整映射
INTERVAL_ADJUSTMENT_MAP: dict[Interval, timedelta] = {
    Interval.MINUTE: timedelta(minutes=1),
    Interval.HOUR: timedelta(hours=1),
    Interval.DAILY: timedelta()
}

# 交易所映射
EXCHANGE_ICE2VT: dict[str, Exchange] = {
    "CFFEX": Exchange.CFFEX,
    "SHFE": Exchange.SHFE,
    "CZCE": Exchange.CZCE,
    "DCE": Exchange.DCE,
    "INE": Exchange.INE,
    "GFEX": Exchange.GFEX,
    "SSE": Exchange.SSE,
    "SZSE": Exchange.SZSE,
}

# 时区常量
CHINA_TZ = ZoneInfo("Asia/Shanghai")


class VoltraderDatafeed(BaseDatafeed):
    """咏春大师的数据服务接口"""

    def __init__(self) -> None:
        """构造函数"""
        self.apppath: str = SETTINGS["datafeed.username"]      # 传参用的字段名
        if not self.apppath:
            self.apppath = "C:/AlgoMaster2/APPs64"             # 默认程序路径

        self.inited: bool = False                              # 初始化状态

        self.api: TCoreAPI = None                              # API实例

        self.symbol_name_map: dict[str, str] = {}              # vt_symbol: ice_symbol

    def init(self, output: Callable = print) -> bool:
        """初始化"""
        # 禁止重复初始化
        if self.inited:
            return True

        # 创建API实例并连接
        self.api = TCoreAPI(apppath=self.apppath)
        self.api.connect()

        # 查询支持的合约代码
        self.query_symbols()

        # 返回初始化状态
        self.inited = True
        return True

    def query_symbols(self) -> None:
        """查询合约"""
        for exchange_str in EXCHANGE_ICE2VT.keys():
            symbols: list = self.api.getallsymbol(exchange=exchange_str)

            for symbol_str in symbols:
                # 查询交易所代码
                symbol_id: str = self.api.getsymbol_id(symbol_str)

                # 保存映射关系
                self.symbol_name_map[symbol_id] = symbol_str

    def query_bar_history(self, req: HistoryRequest, output: Callable = print) -> list[BarData] | None:
        """查询K线数据"""
        if not self.inited:
            n: bool = self.init(output)
            if not n:
                return []

        # 检查合约代码
        name: str | None = self.symbol_name_map.get(req.symbol, None)
        if not name:
            output(f"查询K线数据失败：不支持的合约代码{req.vt_symbol}")
            return []

        # 检查K线周期
        ice_interval, ice_window = INTERVAL_VT2ICE.get(req.interval, ("", ""))
        if not ice_interval:
            output(f"查询K线数据失败：不支持的时间周期{req.interval.value}")
            return []

        # 获取时间戳平移幅度
        adjustment: timedelta = INTERVAL_ADJUSTMENT_MAP[req.interval]

        # 逐日查询K线数据
        all_quote_history: list[dict] = []
        query_start: datetime = req.start

        while query_start < req.end:
            if req.interval in [Interval.DAILY, Interval.HOUR]:
                quote_history: list[dict] = self.api.getquotehistory(
                    ice_interval,
                    ice_window,
                    name,
                    req.start.strftime("%Y%m%d%H"),
                    req.end.strftime("%Y%m%d%H")
                )

                if quote_history:
                    all_quote_history.extend(quote_history)
                break

            query_end: datetime = query_start + timedelta(days=1)

            # 发起K线查询
            quote_history = self.api.getquotehistory(
                ice_interval,
                ice_window,
                name,
                query_start.strftime("%Y%m%d%H"),
                query_end.strftime("%Y%m%d%H")
            )

            # 保存查询结果
            if quote_history:
                all_quote_history.extend(quote_history)

            # 更新查询起始时间
            query_start = query_end

        # 失败则直接返回
        if not all_quote_history:
            output(f"获取{req.symbol}合约{req.start}-{req.end}历史数据失败")
            return []

        # 转换数据格式
        bars: list[BarData] = []

        for history in all_quote_history:
            dt: datetime = (history["DateTime"] - adjustment).replace(tzinfo=CHINA_TZ)
            if req.interval == Interval.DAILY:
                dt = dt.replace(hour=0, minute=0)

            bar: BarData = BarData(
                symbol=req.symbol,
                exchange=req.exchange,
                interval=req.interval,
                datetime=dt,
                open_price=history["Open"],
                high_price=history["High"],
                low_price=history["Low"],
                close_price=history["Close"],
                volume=history["Volume"],
                open_interest=history["OpenInterest"],
                gateway_name="ICETCORE"
            )
            bars.append(bar)

        return bars

    def query_tick_history(self, req: HistoryRequest, output: Callable = print) -> list[TickData] | None:
        """查询Tick数据（暂未支持）"""
        return []
