from tools.toolbase import *
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_response import HandResponse
from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules
from mahjong.tile import TilesConverter
from mahjong.constants import (EAST, WEST, SOUTH, NORTH, HAKU, HATSU, CHUN, FIVE_RED_MAN, FIVE_RED_PIN, FIVE_RED_SOU)
from mahjong.hand_calculating.yaku import Yaku

from mahjong.hand_calculating.yaku_list import (
    AkaDora,
    Chankan,
    Chantai,
    Chiitoitsu,
    Chinitsu,
    Chun,
    DaburuOpenRiichi,
    DaburuRiichi,
    Dora,
    Haitei,
    Haku,
    Hatsu,
    Honitsu,
    Honroto,
    Houtei,
    Iipeiko,
    Ippatsu,
    Ittsu,
    Junchan,
    NagashiMangan,
    OpenRiichi,
    Pinfu,
    Renhou,
    Riichi,
    Rinshan,
    Ryanpeikou,
    Sanankou,
    SanKantsu,
    Sanshoku,
    SanshokuDoukou,
    Shosangen,
    Tanyao,
    Toitoi,
    Tsumo,
    YakuhaiEast,
    YakuhaiNorth,
    YakuhaiOfPlace,
    YakuhaiOfRound,
    YakuhaiSouth,
    YakuhaiWest,
)

from mahjong.hand_calculating.yaku_list.yakuman import (
    Chiihou,
    Chinroutou,
    ChuurenPoutou,
    DaburuChuurenPoutou,
    DaburuKokushiMusou,
    Daichisei,
    Daisangen,
    Daisharin,
    DaiSuushii,
    KokushiMusou,
    Paarenchan,
    RenhouYakuman,
    Ryuuiisou,
    Sashikomi,
    Shousuushii,
    Suuankou,
    SuuankouTanki,
    Suukantsu,
    Tenhou,
    Tsuuiisou,
)

YAKU_CN_NAME = {
    AkaDora: "红宝牌",
    Tsumo: "自摸",
    Chankan: "抢杠",
    Chantai: "混全带幺九",
    Chiitoitsu: "七对子",
    Chinitsu: "清一色",
    Chun: "中",
    DaburuOpenRiichi: "两立直",
    DaburuRiichi: "双立直",
    Dora: "宝牌",
    Haitei: "海底捞月",
    Haku: "白",
    Hatsu: "发",
    Honitsu: "混一色",
    Honroto: "混老头",
    Houtei: "河底捞鱼",
    Iipeiko: "一杯口",
    Ippatsu: "一发",
    Ittsu: "一气通贯",
    Junchan: "纯全带幺九",
    NagashiMangan: "流局满贯",
    OpenRiichi: "明牌立直",
    Pinfu: "平和",
    Renhou: "人和",
    Riichi: "立直",
    Rinshan: "岭上开花",
    Ryanpeikou: "两杯口",
    Sanankou: "三暗刻",
    SanKantsu: "三杠子",
    Sanshoku: "三色同顺",
    SanshokuDoukou: "三色同刻",
    Shosangen: "小三元",
    Tanyao: "断幺九",
    Toitoi: "对对和",
    YakuhaiEast: "东",
    YakuhaiNorth: "北",
    YakuhaiOfPlace: "自风",
    YakuhaiOfRound: "场风",
    YakuhaiSouth: "南",
    YakuhaiWest: "西",    
    # 役满以上   
    Chiihou: "地和",
    Chinroutou: "清老头",
    ChuurenPoutou: "九莲宝灯",
    DaburuChuurenPoutou: "纯正九莲宝灯",
    DaburuKokushiMusou: "国士无双十三面",
    Daichisei: "大七星",
    Daisangen: "大三元",
    Daisharin: "大车轮",
    DaiSuushii: "大四喜",
    KokushiMusou: "国士无双",
    Paarenchan: "八连庄",
    RenhouYakuman: "人和役满",
    Ryuuiisou: "绿一色",
    Sashikomi: "放铳",
    Shousuushii: "小四喜",
    Suuankou: "四暗刻",
    SuuankouTanki: "四暗刻单骑",
    Suukantsu: "四杠子",
    Tenhou: "天和",
    Tsuuiisou: "字一色",    
}

class Tool_Mahjong_Agari(ToolBase):
    """ 麻将和牌计算 """
        
    @property
    def name(self) -> str:
        return "mahjong_agari"
    
    @property
    def desc(self) -> str:
        return "计算日本麻将和牌点数, 番数, 符数, 以及役种"
    
    @property
    def function_json(self) -> dict:
        FUNCTION_BING_SEARCH = {
            "name": "mahjong_agari",
            "description": """计算日本麻将(立直麻将)规则下, 和牌的点数, 番数, 符数, 以及役种。
                输入牌型时, 用m代表万, p代表筒, s代表条, z代表字牌。赤宝牌用0表示, 比如赤五万用0m表示
                对于场风和自风, 用EAST表示东, SOUTH表示南, WEST表示西, NORTH表示北""",
            "parameters": {
                "type": "object",
                "properties": {
                    "hand_tiles": {
                        "type": "string",
                        "description": "手牌, 例: 123456m123p123s11z. 手牌需要包含所有副露的牌, 以及和牌时自摸或荣和的牌(win_tile)"
                    },
                    "win_tile": {
                        "type": "string",
                        "description": "和牌时自摸或者荣和的那张牌。例如: 1p"
                    },
                    "dora_indicators":{
                        "type": "string",
                        "description": "宝牌指示牌列表, 例: 1m3z。可以为空"                      
                    },
                    "round_wind":{
                        "type": "string",
                        "description": "场风. 默认为东风 EAST",
                        "enum": ["EAST", "SOUTH", "WEST", "NORTH"]                    
                    },
                    "player_wind":{
                        "type": "string",
                        "description": "自风. 默认为东风 EAST",
                        "enum": ["EAST", "SOUTH", "WEST", "NORTH"]                    
                    },
                    "is_trumo":{
                        "type": "boolean",
                        "description": "是否自摸, 如果自摸和牌为True, 荣和他人和牌则为False. 默认为自摸 True"
                    },
                    "is_riichi":{
                        "type": "boolean",
                        "description": "是否已经立直, 如果立直则为True。默认为不立直,为False"
                    }                        
                },
                "required": ["hand_tiles","win_tile"]
            }            
        }
        return FUNCTION_BING_SEARCH
    
    def process_toolcall(self, arguments:str, callback_msg:MSG_CALLBACK) -> str:
        """ 计算日麻和牌打点,役种等
        """
        args = json.loads(arguments)
        hand_tiles = TilesConverter.one_line_string_to_136_array(args["hand_tiles"],True)
        
        win_tile = TilesConverter.one_line_string_to_136_array(args["win_tile"],True)[0]
        dora_indi = args.get("dora_indicators", None)
        if not dora_indi:
            dora_indi = None
        else:
            dora_indi = TilesConverter.one_line_string_to_136_array(dora_indi, True)
        
        round_wind = args.get("round_wind", "EAST")
        round_wind = str_to_wind(round_wind)
        player_wind = args.get("player_wind", "EAST")
        player_wind = str_to_wind(player_wind)
        is_trumo = args.get("is_trumo", True)
        is_riichi = args.get("is_riichi", False)
        calculator = HandCalculator()
        
        note = f"正在计算和牌点数{args['hand_tiles']}"
        callback_msg(ChatMsg(ContentType.text, note))
        
        # log_msg = f"计算和牌点数, hand={args['hand_tiles']}, win_tile={args['win_tile']}, dora_indicators={args.get('dora_indicators', None)}"
        # common.logger().info(log_msg)
        config = HandConfig(is_tsumo=is_trumo, is_riichi=is_riichi,
            round_wind=round_wind, player_wind=player_wind,
            options=OptionalRules(has_aka_dora=True, has_open_tanyao=True))
        agari:HandResponse = calculator.estimate_hand_value(hand_tiles, win_tile,
            dora_indicators=dora_indi, config=config)
        if agari.error is not None:
            return agari.error
        
        print_str = f"和牌{agari.cost['total']}点"
        print_str += f"({agari.han}番{agari.fu}符)"
        yaku_str = ','.join([yaku_cn_name(y) for y in agari.yaku])
        print_str += f",役种:[{yaku_str}]"
        print_str += f",条件: 场风={wind_to_str(round_wind)}, 自风={wind_to_str(player_wind)}"
        if is_trumo:
            print_str += ", 自摸"
        else:
            print_str += ", 荣和"
        
                        
        return str(print_str)


def yaku_cn_name(yaku:Yaku) -> str:
  """返回役的中文"""
  yaku_type = type(yaku)
  if yaku_type not in YAKU_CN_NAME:
    return "未知/不存在"
  ret_str = YAKU_CN_NAME[yaku_type]
  
  # 如果是dora, 显示数字个数
  if yaku_type in (AkaDora, Dora):
    ret_str += f"{yaku.han_closed}"
  
  return ret_str


def wind_to_str(wind):
  if wind == EAST:
    return "东"
  elif wind == SOUTH:
    return "南"
  elif wind == WEST:
    return "西"
  elif wind == NORTH:
    return "北"
  else:
    return "错误"

def str_to_wind(wind_str:str):
  if wind_str == "EAST":
    return EAST
  elif wind_str == "SOUTH":
    return SOUTH
  elif wind_str == "WEST":
    return WEST
  elif wind_str == "NORTH":
    return NORTH
  else:
    return None