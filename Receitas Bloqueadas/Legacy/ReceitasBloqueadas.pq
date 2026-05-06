let
    Fonte = OBsReceitasBloqueadas,
    #"Outras Colunas Removidas" = Table.SelectColumns(Fonte,{"Cor Rec.", "EP Rec.", "PE Rec", "Data Última Prod.", "Data Bloqueio"}),
    #"Duplicatas Removidas" = Table.Distinct(#"Outras Colunas Removidas"),
    #"Linhas Classificadas" = Table.Sort(#"Duplicatas Removidas",{{"Cor Rec.", Order.Ascending}, {"EP Rec.", Order.Ascending}}),
    #"Personalização Adicionada" = Table.AddColumn(#"Linhas Classificadas", "Previsão de Liberar", each "")
in
    #"Personalização Adicionada"