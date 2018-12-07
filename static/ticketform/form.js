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
		return;
	}

	var topic = topics_table[topic_id];

	$('#topic_desc').html(topic['form_description']).toggle(topic['form_description'] != "");
	$('#mediainfo-group').toggle(topic['ticket_media']);
	$('#expediture-group').toggle(topic['ticket_expenses']);
	$('#preexpediture-group').toggle(topic['ticket_preexpenses']);
	$('.field_car_travel').toggle(topic['ticket_statutory_declaration']);
}

function refresh_subtopic_description()
{
	var subtopic_id = $('#id_subtopic').val();
	if (subtopic_id == "")
	{
		$('#subtopic_desc').hide();
		return;
	}

	var subtopic = subtopics_table[subtopic_id];

	$('#subtopic_desc').html(subtopic['form_description']).toggle(subtopic['form_description'] != '');
}

$(document).ready(function() {
	$('#id_topic').change(refresh_description);
	$('#id_topic').change(refresh_subtopic_description);
	$('#id_subtopic').change(refresh_subtopic_description);
	refresh_description();
	refresh_subtopic_description();
});
