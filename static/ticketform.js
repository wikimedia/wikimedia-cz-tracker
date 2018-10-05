function refresh_description()
{
	var topic_id = $('#id_topic').val();
	if (topic_id == '')
	{
		$('#topic_desc').hide();
		$('#mediainfo-group').hide();
		$('#expediture-group').hide();
		$('#preexpediture-group').hide();
		$('.field_car_travel').hide();
		$('#id_subtopic').html("<option value selected>---------</option>");
		return;
	}

	var topic = topics_table[topic_id];
	$('#topic_desc').html(topic['form_description']).toggle(topic['form_description'] != "");
	$('#mediainfo-group').toggle(topic['ticket_media']);
	$('#expediture-group').toggle(topic['ticket_expenses']);
	$('#preexpediture-group').toggle(topic['ticket_preexpenses']);
	$('.field_car_travel').toggle(topic['ticket_statutory_declaration']);
	var subtopicsHtml = "<option value selected>---------</option>";
	for(var i = 0; i < topic.subtopic_set.length; i++)
	{
		var subtopic = topic.subtopic_set[i];
		subtopicsHtml += '<option value="' + subtopic.id + '">' + subtopic.display_name + '</option>';
	}
	$('#id_subtopic').html(subtopicsHtml);
	if($('#id_subtopic').html().includes(window.originallyCheckedTag))
		$('#id_subtopic').val(window.originallyCheckedTag);
	else
		$('#id_subtopic').val("");
}

function statutory_declaration() {
	$('.field_statutory_declaration').toggle($('#id_car_travel').prop('checked'));
}

$(document).ready(function() {
	$('#id_topic').change(refresh_description);
	$('.field_car_travel').change(statutory_declaration);
	window.originallyCheckedTag = $('#id_subtopic').val();
	refresh_description();
	statutory_declaration();
});
